"""Cálculos de insights puros sobre os DataFrames das camadas Bronze/Silver."""

import unicodedata
import zlib

import pandas as pd


def pct_change(current: float, previous: float | None) -> float | None:
    """Variação percentual de `previous` para `current`, ou None se não houver base."""
    if not previous:
        return None
    return (current - previous) / previous


def compute_price_alerts(
    df_bronze: pd.DataFrame, threshold: float = 0.15
) -> pd.DataFrame:
    """Produtos cujo último preço registrado subiu mais que `threshold` frente à média anterior."""
    if df_bronze.empty:
        return pd.DataFrame()

    alerts = []
    for product_id, group in df_bronze.sort_values("purchase_date").groupby(
        "product_id"
    ):
        if len(group) < 2:
            continue
        last_price = group["product_price"].iloc[-1]
        prior_avg = group["product_price"].iloc[:-1].mean()
        variation = pct_change(last_price, prior_avg)
        if variation is not None and variation > threshold:
            alerts.append(
                {
                    "product_id": product_id,
                    "last_price": last_price,
                    "prior_avg_price": prior_avg,
                    "variation_pct": variation,
                    "last_purchase_date": group["purchase_date"].iloc[-1],
                }
            )

    if not alerts:
        return pd.DataFrame()
    return pd.DataFrame(alerts).sort_values("variation_pct", ascending=False)


def _recurrence_gap_frame(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Linhas de compra com a coluna `gap` = dias desde a compra anterior
    (do mesmo grupo `keys`). Primeira compra de cada grupo é descartada."""
    ordered = df.sort_values([*keys, "purchase_date"]).copy()
    ordered["gap"] = ordered.groupby(keys, sort=False)["purchase_date"].diff().dt.days
    ordered = ordered.dropna(subset=["gap"])
    return ordered[ordered["gap"] >= 0]


def compute_recurrence_curve(
    df_bronze: pd.DataFrame, max_days: int = 60
) -> pd.DataFrame:
    """ECDF do intervalo entre compras consecutivas do mesmo produto.

    Formato longo: `scope` ("Total" ou nome do mercado), `days` (0..max_days) e
    `cumulative_pct` (fração das recompras já ocorridas até aquele dia).
    """
    cols = ["scope", "days", "cumulative_pct"]
    if df_bronze.empty:
        return pd.DataFrame(columns=cols)

    df = df_bronze.copy()
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])

    series: dict[str, pd.Series] = {
        "Total": _recurrence_gap_frame(df, ["product_id"])["gap"]
    }
    by_market = _recurrence_gap_frame(df, ["market_id", "product_id"])
    for market, grp in by_market.groupby("market_id"):
        series[market] = grp["gap"]

    rows = []
    for scope, gaps in series.items():
        if gaps.empty:
            continue
        n = len(gaps)
        rows += [
            {"scope": scope, "days": d, "cumulative_pct": (gaps <= d).sum() / n}
            for d in range(max_days + 1)
        ]
    return pd.DataFrame(rows, columns=cols)


# Tokens de cor do tema (.streamlit/config.toml)
_MARKET_FIXED_COLORS = {"swift": "#F59E0B", "atacadao": "#22C55E"}
_TOTAL_COLOR = "#94A3B8"  # grayColor
_MARKET_FALLBACK_PALETTE = ["#3B82F6", "#38BDF8", "#8B5CF6", "#EF4444", "#14B8A6"]


def _norm_market(name: str) -> str:
    """Normaliza nome de mercado: sem acento, sem espaços nas pontas, minúsculo."""
    ascii_name = (
        unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    )
    return ascii_name.strip().lower()


def market_color(name: str) -> str:
    """Cor determinística de um mercado (ou de 'Total').

    Swift/Atacadão têm cor fixa; os demais recebem uma cor estável derivada do
    nome (crc32 → paleta), então não muda entre reruns nem sessões.
    """
    if str(name) == "Total":
        return _TOTAL_COLOR
    key = _norm_market(name)
    if key in _MARKET_FIXED_COLORS:
        return _MARKET_FIXED_COLORS[key]
    idx = zlib.crc32(key.encode()) % len(_MARKET_FALLBACK_PALETTE)
    return _MARKET_FALLBACK_PALETTE[idx]
