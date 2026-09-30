"""Leitura das camadas Silver/Bronze em DataFrames (sem dependência de UI).

Cada loader engole exceções e devolve um DataFrame vazio se a tabela ainda não
existir (instalação nova).
"""

import pandas as pd

from shopping_list.database import DatabaseManager


def load_product_stats(db: DatabaseManager) -> pd.DataFrame:
    """Carrega estatísticas de produtos da camada Silver."""
    try:
        df = pd.read_sql("SELECT * FROM silver_product_stats", con=db.engine("silver"))
        if not df.empty:
            numeric_cols = [
                "avg_days_purchase",
                "avg_product_price",
                "min_product_price",
                "max_product_price",
                "days_last_purchase",
            ]
            df[numeric_cols] = df[numeric_cols].astype(float)
            df["buy"] = df["days_last_purchase"] > df["avg_days_purchase"]
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_market_stats(db: DatabaseManager) -> pd.DataFrame:
    """Carrega estatísticas de mercados da camada Silver."""
    try:
        df = pd.read_sql("SELECT * FROM silver_market_stats", con=db.engine("silver"))
        if not df.empty:
            df[["total_spent", "avg_ticket"]] = df[
                ["total_spent", "avg_ticket"]
            ].astype(float)
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_monthly_spending(db: DatabaseManager) -> pd.DataFrame:
    """Carrega gastos mensais da camada Silver."""
    try:
        df = pd.read_sql(
            "SELECT * FROM silver_monthly_spending", con=db.engine("silver")
        )
        if not df.empty:
            df[["total_spent", "avg_price"]] = df[["total_spent", "avg_price"]].astype(
                float
            )
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def load_bronze_data(db: DatabaseManager) -> pd.DataFrame:
    """Carrega dados da camada Bronze para análises detalhadas."""
    try:
        df = pd.read_sql(
            "SELECT purchase_date, product_id, product_price, market_id "
            "FROM bronze_purchases ORDER BY purchase_date",
            con=db.engine("bronze"),
        )
        if not df.empty:
            df["product_price"] = df["product_price"].astype(float)
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
