"""
SQLAlchemy models for the Medallion Architecture (Raw → Bronze → Silver).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# =============================================================================
# RAW Layer — Database: raw
# Dados brutos, exatamente como chegam (append-only)
# =============================================================================


class RawPurchase(Base):
    __tablename__ = "raw_purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_date = Column(String(50), nullable=False)
    product_id = Column(String(100), nullable=False)
    product_price = Column(String(50), nullable=False)
    quantity = Column(String(50), nullable=True)
    unit_price = Column(String(50), nullable=True)
    market_id = Column(String(100), nullable=False)
    access_key = Column(String(44), nullable=True)
    nfce_url = Column(String(512), nullable=True)
    ingested_at = Column(DateTime, default=datetime.now, nullable=False)
    source_type = Column(String(20), nullable=False, default="manual")


# =============================================================================
# BRONZE Layer — Database: bronze
# Dados limpos, tipados e normalizados
# =============================================================================


class BronzePurchase(Base):
    __tablename__ = "bronze_purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_date = Column(Date, nullable=False)
    product_id = Column(String(100), nullable=False)
    product_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Numeric(10, 3), nullable=True)
    unit_price = Column(Numeric(10, 2), nullable=True)
    market_id = Column(String(100), nullable=False)
    access_key = Column(String(44), nullable=True)
    nfce_url = Column(String(512), nullable=True)
    raw_id = Column(Integer, nullable=False)
    processed_at = Column(DateTime, default=datetime.now, nullable=False)


# =============================================================================
# SILVER Layer — Database: silver
# Dados agregados e prontos para análise
# =============================================================================


class SilverProductStats(Base):
    __tablename__ = "silver_product_stats"

    product_id = Column(String(100), primary_key=True)
    last_purchase_date = Column(Date, nullable=False)
    avg_days_purchase = Column(Numeric(10, 2))
    avg_product_price = Column(Numeric(10, 2), nullable=False)
    min_product_price = Column(Numeric(10, 2), nullable=False)
    max_product_price = Column(Numeric(10, 2), nullable=False)
    total_purchases = Column(Integer, nullable=False)
    days_last_purchase = Column(Numeric(10, 2), nullable=False)


class SilverMarketStats(Base):
    __tablename__ = "silver_market_stats"

    market_id = Column(String(100), primary_key=True)
    total_spent = Column(Numeric(12, 2), nullable=False)
    avg_ticket = Column(Numeric(10, 2), nullable=False)
    visit_count = Column(Integer, nullable=False)
    last_visit = Column(Date, nullable=False)


class SilverMonthlySpending(Base):
    __tablename__ = "silver_monthly_spending"

    year_month = Column(String(7), primary_key=True)
    total_spent = Column(Numeric(12, 2), nullable=False)
    item_count = Column(Integer, nullable=False)
    avg_price = Column(Numeric(10, 2), nullable=False)
