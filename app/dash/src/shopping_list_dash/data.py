"""Data access for the dashboard: the MySQL-backed loader and a short TTL cache."""

import logging
import time
from collections.abc import Callable

from shopping_list.database import DatabaseManager
from shopping_list.loaders import (
    load_bronze_data,
    load_market_stats,
    load_monthly_spending,
    load_product_stats,
)
from shopping_list_dash.views import DashboardData

log = logging.getLogger(__name__)

Loader = Callable[[], DashboardData]

_db: DatabaseManager | None = None


def load_from_database() -> DashboardData:
    """Read the Silver aggregates and Bronze lines. Never raises: errors become `data.error`."""
    global _db
    try:
        if _db is None:
            _db = DatabaseManager()
        return DashboardData(
            products=load_product_stats(_db),
            markets=load_market_stats(_db),
            monthly=load_monthly_spending(_db),
            bronze=load_bronze_data(_db),
        )
    except Exception as exc:
        log.exception("Could not load dashboard data")
        return DashboardData(
            error=f"Could not reach the database ({type(exc).__name__})."
        )


def cached(loader: Loader, ttl: float = 30.0) -> Loader:
    """Reuse the last result for `ttl` seconds (one page load triggers several callbacks)."""
    state: dict = {"at": 0.0, "data": None}

    def wrapper() -> DashboardData:
        now = time.monotonic()
        if state["data"] is None or now - state["at"] > ttl:
            state["data"], state["at"] = loader(), now
        return state["data"]

    return wrapper
