"""
ETL Pipeline for the Medallion Architecture.
Handles data transformation: Raw → Bronze → Silver.
"""

from datetime import UTC, datetime

import pandas as pd
import sqlalchemy

from src.database import DatabaseManager


class ETLPipeline:
    """Pipeline de transformação entre camadas do medallion."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def _read_sql_file(self, path: str) -> str:
        with open(path, "r") as f:
            return f.read()

    # =========================================================================
    # RAW → BRONZE
    # =========================================================================

    def raw_to_bronze(self) -> int:
        """
        Lê dados novos de raw_purchases (não processados),
        limpa/normaliza, e insere em bronze_purchases.
        Retorna o número de registros processados.
        """
        raw_engine = self.db.engine("raw")
        bronze_engine = self.db.engine("bronze")

        # Buscar IDs já processados na bronze
        try:
            existing_ids = pd.read_sql(
                "SELECT DISTINCT raw_id FROM bronze_purchases",
                con=bronze_engine,
            )["raw_id"].tolist()
        except Exception:  # noqa: BLE001
            existing_ids = []

        # Buscar dados novos da raw
        query = "SELECT * FROM raw_purchases"
        df_raw = pd.read_sql(query, con=raw_engine)

        if df_raw.empty:
            return 0

        # Filtrar apenas registros não processados
        if existing_ids:
            df_raw = df_raw[~df_raw["id"].isin(existing_ids)]

        if df_raw.empty:
            return 0

        # ---- Transformações Bronze ----
        df_bronze = pd.DataFrame()
        df_bronze["raw_id"] = df_raw["id"]
        df_bronze["purchase_date"] = pd.to_datetime(
            df_raw["purchase_date"], format="mixed", dayfirst=False
        ).dt.date
        df_bronze["product_id"] = df_raw["product_id"].str.strip().str.title()
        df_bronze["product_price"] = pd.to_numeric(
            df_raw["product_price"], errors="coerce"
        )

        # quantidade / custo unitário — product_price permanece o total da linha.
        # Regra: quantity ausente/<=0 -> 1; unit_price ausente -> total/quantity;
        # total ausente -> unit_price*quantity; havendo ambos, o total prevalece.
        raw_qty = (
            df_raw["quantity"]
            if "quantity" in df_raw.columns
            else pd.Series(index=df_raw.index, dtype="object")
        )
        raw_unit = (
            df_raw["unit_price"]
            if "unit_price" in df_raw.columns
            else pd.Series(index=df_raw.index, dtype="object")
        )
        quantity = pd.to_numeric(raw_qty, errors="coerce")
        quantity = quantity.where(quantity > 0).fillna(1)
        unit_price = pd.to_numeric(raw_unit, errors="coerce")
        total = df_bronze["product_price"]
        unit_price = unit_price.where(unit_price.notna(), total / quantity)
        total = total.where(total.notna(), unit_price * quantity)
        df_bronze["quantity"] = quantity.round(3)
        df_bronze["unit_price"] = unit_price.round(2)
        df_bronze["product_price"] = total.round(2)

        df_bronze["market_id"] = df_raw["market_id"].str.strip().str.title()

        # Metadados da NFC-e (por nota): apenas strip + vazio -> NULL, sem title-case.
        for col in ("access_key", "nfce_url"):
            if col in df_raw.columns:
                cleaned = df_raw[col].astype("string").str.strip()
                df_bronze[col] = cleaned.replace(
                    {"": pd.NA, "nan": pd.NA, "None": pd.NA}
                )
            else:
                df_bronze[col] = pd.NA

        df_bronze["processed_at"] = datetime.now(tz=UTC)

        # Remover registros com preço inválido
        df_bronze = df_bronze.dropna(subset=["product_price"])

        if df_bronze.empty:
            return 0

        # Inserir na bronze
        df_bronze.to_sql(
            "bronze_purchases",
            con=bronze_engine,
            if_exists="append",
            index=False,
        )

        return len(df_bronze)

    # =========================================================================
    # BRONZE → SILVER
    # =========================================================================

    def bronze_to_silver(self):
        """
        Agrega dados de bronze_purchases e atualiza as tabelas silver.
        Usa truncate + insert para cada tabela silver.
        """
        bronze_engine = self.db.engine("bronze")
        silver_engine = self.db.engine("silver")

        # --- Product Stats ---
        query = sqlalchemy.text(self._read_sql_file("src/query/product_stats.sql"))
        df_product = pd.read_sql(query, con=bronze_engine)
        if not df_product.empty:
            with silver_engine.connect() as conn:
                conn.execute(sqlalchemy.text("DELETE FROM silver_product_stats"))
                conn.commit()
            df_product.to_sql(
                "silver_product_stats",
                con=silver_engine,
                if_exists="append",
                index=False,
            )

        # --- Market Stats ---
        query = sqlalchemy.text(self._read_sql_file("src/query/market_stats.sql"))
        df_market = pd.read_sql(query, con=bronze_engine)
        if not df_market.empty:
            with silver_engine.connect() as conn:
                conn.execute(sqlalchemy.text("DELETE FROM silver_market_stats"))
                conn.commit()
            df_market.to_sql(
                "silver_market_stats",
                con=silver_engine,
                if_exists="append",
                index=False,
            )

        # --- Monthly Spending ---
        query = sqlalchemy.text(self._read_sql_file("src/query/monthly_spending.sql"))
        df_monthly = pd.read_sql(query, con=bronze_engine)
        if not df_monthly.empty:
            with silver_engine.connect() as conn:
                conn.execute(sqlalchemy.text("DELETE FROM silver_monthly_spending"))
                conn.commit()
            df_monthly.to_sql(
                "silver_monthly_spending",
                con=silver_engine,
                if_exists="append",
                index=False,
            )

    # =========================================================================
    # Pipeline Completo
    # =========================================================================

    def run_pipeline(self) -> int:
        """Executa o pipeline completo: Raw → Bronze → Silver."""
        records_processed = self.raw_to_bronze()
        self.bronze_to_silver()
        return records_processed

    # =========================================================================
    # Migração de dados legados
    # =========================================================================

    def migrate_legacy_data(self):
        """
        Migra dados da tabela legada shopping_list (database raw)
        para a nova estrutura raw_purchases.
        Executa apenas uma vez.
        """
        raw_engine = self.db.engine("raw")

        # Verificar se a tabela legada existe
        inspector = sqlalchemy.inspect(raw_engine)
        if "shopping_list" not in inspector.get_table_names():
            return 0

        # Verificar se já foi migrado (raw_purchases já tem dados)
        try:
            count = pd.read_sql(
                "SELECT COUNT(*) as cnt FROM raw_purchases", con=raw_engine
            )["cnt"].iloc[0]
            if count > 0:
                return 0
        except Exception:  # noqa: BLE001, S110
            pass  # Table doesn't exist yet, will be created

        # Migrar dados
        df_legacy = pd.read_sql("SELECT * FROM shopping_list", con=raw_engine)
        if df_legacy.empty:
            return 0

        df_raw = pd.DataFrame()
        df_raw["purchase_date"] = df_legacy["purchase_date"].astype(str)
        df_raw["product_id"] = df_legacy["product_id"]
        df_raw["product_price"] = df_legacy["product_price"].astype(str)
        df_raw["market_id"] = df_legacy["market_id"]
        df_raw["ingested_at"] = datetime.now(tz=UTC)
        df_raw["source_type"] = "migration"

        df_raw.to_sql(
            "raw_purchases",
            con=raw_engine,
            if_exists="append",
            index=False,
        )

        return len(df_raw)
