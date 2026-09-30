"""Framework-free view models: every number the dashboard shows is computed here."""

from dataclasses import dataclass, field

import pandas as pd

from shopping_list.analytics import (
    compute_price_alerts,
    compute_recurrence_curve,
    pct_change,
)


@dataclass
class DashboardData:
    """Silver aggregates + Bronze purchase lines, as returned by `shopping_list.loaders`."""

    products: pd.DataFrame = field(default_factory=pd.DataFrame)
    markets: pd.DataFrame = field(default_factory=pd.DataFrame)
    monthly: pd.DataFrame = field(default_factory=pd.DataFrame)
    bronze: pd.DataFrame = field(default_factory=pd.DataFrame)
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.products.empty and self.monthly.empty


@dataclass
class Kpi:
    label: str
    value: str
    note: str
    help: str
    tone: str = "neutral"  # "good" | "bad" | "neutral"


def latest_purchase(data: DashboardData):
    if data.bronze.empty:
        return None
    return pd.to_datetime(data.bronze["purchase_date"]).max()


# -----------------------------------------------------------------------------
# Header KPIs
# -----------------------------------------------------------------------------


def _tone_for_spending(change: float | None, tolerance: float = 0.02) -> str:
    if change is None or abs(change) < tolerance:
        return "neutral"
    return "bad" if change > 0 else "good"


def build_kpis(data: DashboardData, fmt) -> list[Kpi]:
    """`fmt` is the formatting module (injected so the view model stays UI-free)."""
    kpis: list[Kpi] = []

    monthly = data.monthly.sort_values("year_month") if not data.monthly.empty else None
    if monthly is not None:
        last = monthly.iloc[-1]
        previous = float(monthly["total_spent"].iloc[-2]) if len(monthly) > 1 else None
        change = pct_change(float(last["total_spent"]), previous)
        kpis.append(
            Kpi(
                "Latest month",
                fmt.brl(last["total_spent"]),
                f"{fmt.pct(change)} vs. previous month"
                if change is not None
                else fmt.month_label(last["year_month"]),
                f"Total spent in {fmt.month_label(last['year_month'])}.",
                _tone_for_spending(change),
            )
        )
        kpis.append(
            Kpi(
                "Total spent",
                fmt.brl(monthly["total_spent"].sum(), 0),
                f"over {len(monthly)} months tracked",
                "Sum of every purchase line imported so far.",
            )
        )

    if not data.markets.empty:
        visits = int(data.markets["visit_count"].sum())
        avg_ticket = data.markets["total_spent"].sum() / visits if visits else None
        kpis.append(
            Kpi(
                "Average ticket",
                fmt.brl(avg_ticket),
                f"across {fmt.integer(visits)} store visits",
                "Total spent divided by the number of distinct shopping trips.",
            )
        )

    if not data.products.empty:
        due = int(data.products["buy"].sum())
        kpis.append(
            Kpi(
                "Items to restock",
                fmt.integer(due),
                f"of {fmt.integer(len(data.products))} products tracked",
                "Products whose days since last purchase exceed their average repurchase interval.",
                "bad" if due else "good",
            )
        )
    return kpis


# -----------------------------------------------------------------------------
# Tab: Shopping list
# -----------------------------------------------------------------------------


def shopping_list_frame(products: pd.DataFrame) -> pd.DataFrame:
    """Products due for purchase, most overdue (relative to their own rhythm) first."""
    cols = [
        "product_id",
        "last_purchase_date",
        "days_last_purchase",
        "avg_days_purchase",
        "overdue_days",
        "avg_product_price",
        "total_purchases",
    ]
    if products.empty:
        return pd.DataFrame(columns=cols)
    due = products[products["buy"]].copy()
    due = due[due["avg_days_purchase"].notna() & (due["avg_days_purchase"] > 0)]
    due["overdue_days"] = due["days_last_purchase"] - due["avg_days_purchase"]
    due["overdue_ratio"] = due["days_last_purchase"] / due["avg_days_purchase"]
    return due.sort_values("overdue_ratio", ascending=False)[cols].reset_index(
        drop=True
    )


def upcoming_frame(products: pd.DataFrame, horizon: int = 7) -> pd.DataFrame:
    """Products not yet due that will be within `horizon` days."""
    if products.empty:
        return pd.DataFrame(columns=["product_id", "due_in_days"])
    df = products[~products["buy"] & products["avg_days_purchase"].notna()].copy()
    df["due_in_days"] = df["avg_days_purchase"] - df["days_last_purchase"]
    df = df[df["due_in_days"].between(0, horizon)]
    return df.sort_values("due_in_days")[["product_id", "due_in_days"]].reset_index(
        drop=True
    )


# -----------------------------------------------------------------------------
# Tab: Prices
# -----------------------------------------------------------------------------


def product_options(products: pd.DataFrame, bronze: pd.DataFrame) -> list[str]:
    """Products ordered by purchase count (most bought first)."""
    if not products.empty:
        return products.sort_values("total_purchases", ascending=False)[
            "product_id"
        ].tolist()
    if not bronze.empty:
        return bronze["product_id"].value_counts().index.tolist()
    return []


def price_history(bronze: pd.DataFrame, product_id: str | None) -> pd.DataFrame:
    if bronze.empty or not product_id:
        return pd.DataFrame(columns=["purchase_date", "product_price", "market_id"])
    df = bronze[bronze["product_id"] == product_id].copy()
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])
    return df.sort_values("purchase_date")


def price_summary(products: pd.DataFrame, product_id: str | None) -> dict | None:
    if products.empty or not product_id:
        return None
    row = products[products["product_id"] == product_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def price_alerts(
    bronze: pd.DataFrame, threshold: float = 0.15, limit: int = 15
) -> pd.DataFrame:
    alerts = compute_price_alerts(bronze, threshold)
    return alerts.head(limit).reset_index(drop=True)


# -----------------------------------------------------------------------------
# Tab: Markets
# -----------------------------------------------------------------------------


def markets_frame(markets: pd.DataFrame) -> pd.DataFrame:
    if markets.empty:
        return markets
    df = markets.copy()
    total = df["total_spent"].sum()
    df["share"] = df["total_spent"] / total if total else 0.0
    return df.sort_values("total_spent", ascending=False).reset_index(drop=True)


# -----------------------------------------------------------------------------
# Tab: Trends
# -----------------------------------------------------------------------------


def monthly_frame(monthly: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    if monthly.empty:
        return monthly
    df = monthly.sort_values("year_month").reset_index(drop=True).copy()
    df["rolling_avg"] = df["total_spent"].rolling(window, min_periods=1).mean()
    return df


def recurrence_frame(bronze: pd.DataFrame, max_days: int = 60) -> pd.DataFrame:
    return compute_recurrence_curve(bronze, max_days)


def median_repurchase_days(curve: pd.DataFrame) -> float | None:
    """First day at which half of the repurchases (all markets) have happened."""
    total = curve[curve["scope"] == "Total"] if not curve.empty else curve
    if total.empty:
        return None
    reached = total[total["cumulative_pct"] >= 0.5]
    return float(reached["days"].iloc[0]) if not reached.empty else None
