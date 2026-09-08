"""
Database manager for the Medallion Architecture.
Manages connections to the 3 databases: raw, bronze, silver.
"""

import os

import sqlalchemy

USER = os.getenv("MYSQL_USER")
PASSWORD = os.getenv("MYSQL_PASSWORD")
HOST = os.getenv("MYSQL_HOST")
PORT = int(os.getenv("MYSQL_PORT", "3306"))

DATABASES = ["raw", "bronze", "silver"]

# Colunas adicionadas depois da criação original das tabelas. `create_all_tables`
# só cria tabela faltante (nunca faz ALTER), então essas evoluções aditivas de
# schema são aplicadas por `DatabaseManager.migrate_schema`.
SCHEMA_ADDITIONS: dict[tuple[str, str], dict[str, str]] = {
    ("raw", "raw_purchases"): {
        "quantity": "VARCHAR(50) NULL",
        "unit_price": "VARCHAR(50) NULL",
        "access_key": "VARCHAR(44) NULL",
        "nfce_url": "VARCHAR(512) NULL",
    },
    ("bronze", "bronze_purchases"): {
        "quantity": "DECIMAL(10,3) NULL",
        "unit_price": "DECIMAL(10,2) NULL",
        "access_key": "VARCHAR(44) NULL",
        "nfce_url": "VARCHAR(512) NULL",
    },
}


class DatabaseManager:
    """Gerencia engines e sessões para os 3 databases do medallion."""

    def __init__(self):
        self._engines: dict[str, sqlalchemy.Engine] = {}
        self._admin_engine = self._create_engine(database=None)

        self.create_databases()

        for db_name in DATABASES:
            self._engines[db_name] = self._create_engine(database=db_name)

    def _create_engine(self, database: str | None) -> sqlalchemy.Engine:
        url = sqlalchemy.engine.URL.create(
            drivername="mysql+pymysql",
            username=USER,
            password=PASSWORD,
            host=HOST,
            port=PORT,
            database=database,
        )
        return sqlalchemy.create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    def create_databases(self):
        """Cria os 3 databases se não existirem."""
        with self._admin_engine.connect() as conn:
            for db_name in DATABASES:
                conn.execute(
                    sqlalchemy.text(
                        f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
            conn.commit()

    def create_all_tables(self):
        """Cria todas as tabelas nos databases correspondentes."""
        from src.models import (
            BronzePurchase,
            RawPurchase,
            SilverMarketStats,
            SilverMonthlySpending,
            SilverProductStats,
        )

        # Raw tables
        raw_tables = [RawPurchase.__table__]
        raw_metadata = sqlalchemy.MetaData()
        for table in raw_tables:
            table.to_metadata(raw_metadata)
        raw_metadata.create_all(self.engine("raw"))

        # Bronze tables
        bronze_tables = [BronzePurchase.__table__]
        bronze_metadata = sqlalchemy.MetaData()
        for table in bronze_tables:
            table.to_metadata(bronze_metadata)
        bronze_metadata.create_all(self.engine("bronze"))

        # Silver tables
        silver_tables = [
            SilverProductStats.__table__,
            SilverMarketStats.__table__,
            SilverMonthlySpending.__table__,
        ]
        silver_metadata = sqlalchemy.MetaData()
        for table in silver_tables:
            table.to_metadata(silver_metadata)
        silver_metadata.create_all(self.engine("silver"))

    def migrate_schema(self):
        """Aplica evoluções aditivas de schema (ADD COLUMN) idempotentemente.

        MySQL não tem `ADD COLUMN IF NOT EXISTS`, então inspeciona as colunas
        existentes antes de cada ALTER. Instalações novas caem aqui sem trabalho,
        pois `create_all_tables` já criou as colunas.
        """
        for (layer, table), columns in SCHEMA_ADDITIONS.items():
            engine = self.engine(layer)
            existing = {
                col["name"] for col in sqlalchemy.inspect(engine).get_columns(table)
            }
            missing = {
                name: ddl for name, ddl in columns.items() if name not in existing
            }
            if not missing:
                continue

            with engine.begin() as conn:
                for name, ddl in missing.items():
                    conn.execute(
                        sqlalchemy.text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                    )
                if table == "bronze_purchases":
                    conn.execute(
                        sqlalchemy.text(
                            "UPDATE bronze_purchases SET quantity = 1 "
                            "WHERE quantity IS NULL"
                        )
                    )
                    conn.execute(
                        sqlalchemy.text(
                            "UPDATE bronze_purchases SET unit_price = product_price "
                            "WHERE unit_price IS NULL"
                        )
                    )

    def engine(self, layer: str) -> sqlalchemy.Engine:
        """Retorna o engine para uma camada específica."""
        if layer not in self._engines:
            raise ValueError(f"Unknown layer: {layer}. Must be one of {DATABASES}")
        return self._engines[layer]
