"""Number and date formatting for the English UI (R$ amounts, ISO dates)."""

import math
from datetime import date, datetime

import pandas as pd

MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def _missing(value) -> bool:
    return (
        value is None
        or (isinstance(value, float) and math.isnan(value))
        or value is pd.NaT
    )


def brl(value, decimals: int = 2) -> str:
    if _missing(value):
        return "—"
    return f"R$ {value:,.{decimals}f}"


def pct(value, signed: bool = True) -> str:
    if _missing(value):
        return "—"
    return f"{value:+.1%}" if signed else f"{value:.1%}"


def integer(value) -> str:
    if _missing(value):
        return "—"
    return f"{round(value):,}"


def days(value) -> str:
    if _missing(value):
        return "—"
    n = round(value)
    return f"{n} day" if n == 1 else f"{n} days"


def month_label(year_month: str) -> str:
    """'2026-03' -> 'Mar 2026'."""
    year, month = str(year_month).split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def iso_date(value) -> str:
    if _missing(value):
        return "—"
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]
