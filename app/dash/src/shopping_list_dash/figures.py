"""Pure Plotly figures. Every figure goes through `theme.plotly_layout()`."""

import pandas as pd
import plotly.graph_objects as go

from shopping_list.analytics import market_color
from shopping_list_dash import formatting as fmt
from shopping_list_dash.theme import (
    ACCENT,
    AVERAGE,
    BAD,
    LEGEND_TOP,
    MUTED,
    TEXT,
    plotly_layout,
)


def ranked_bars(
    labels: pd.Series,
    values: pd.Series,
    text: list[str],
    colors: list[str] | str = ACCENT,
    top: int = 12,
) -> go.Figure:
    """Horizontal ranked bars, largest on top, value label on the bar, value axis hidden."""
    df = pd.DataFrame({"label": labels, "value": values, "text": text})
    if not isinstance(colors, str):
        df["color"] = colors
    df = df.nlargest(top, "value").iloc[::-1]
    fig = go.Figure(
        go.Bar(
            y=df["label"],
            x=df["value"],
            orientation="h",
            text=df["text"],
            textposition="outside",
            textfont={"color": TEXT},
            cliponaxis=False,
            marker={"color": df.get("color", colors)},
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    fig.update_layout(
        plotly_layout(
            height=60 + 34 * len(df),
            margin={"l": 8, "r": 90, "t": 8, "b": 8},
            xaxis={"visible": False},
            yaxis={"showgrid": False, "title": None, "ticksuffix": "  ", "color": TEXT},
            bargap=0.3,
        )
    )
    return fig


def overdue_bars(due: pd.DataFrame) -> go.Figure:
    return ranked_bars(
        due["product_id"],
        due["overdue_days"],
        [f"+{fmt.days(v)}" for v in due["overdue_days"]],
        colors=BAD,
    )


def market_spend_bars(markets: pd.DataFrame) -> go.Figure:
    return ranked_bars(
        markets["market_id"],
        markets["total_spent"],
        [
            f"{fmt.brl(v, 0)} · {fmt.pct(s, signed=False)}"
            for v, s in zip(markets["total_spent"], markets["share"], strict=True)
        ],
        colors=[market_color(m) for m in markets["market_id"]],
    )


def market_ticket_bars(markets: pd.DataFrame) -> go.Figure:
    return ranked_bars(
        markets["market_id"],
        markets["avg_ticket"],
        [fmt.brl(v) for v in markets["avg_ticket"]],
        colors=[market_color(m) for m in markets["market_id"]],
    )


def price_history_lines(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for market, grp in history.groupby("market_id", sort=True):
        fig.add_trace(
            go.Scatter(
                x=grp["purchase_date"],
                y=grp["product_price"],
                mode="lines+markers",
                name=str(market),
                line={"color": market_color(market), "width": 2},
                marker={"size": 7},
                hovertemplate=f"{market}<br>%{{x|%Y-%m-%d}}: R$ %{{y:,.2f}}<extra></extra>",
            )
        )
    fig.update_layout(
        plotly_layout(
            height=340,
            showlegend=True,
            legend=LEGEND_TOP,
            yaxis={
                "showgrid": True,
                "gridcolor": "#262B36",
                "zeroline": False,
                "title": None,
                "tickprefix": "R$ ",
                "tickformat": ",.2f",
            },
            xaxis={
                "showgrid": False,
                "zeroline": False,
                "title": None,
                "tickformat": "%b %Y",
            },
        )
    )
    return fig


def monthly_bars(monthly: pd.DataFrame) -> go.Figure:
    labels = [fmt.month_label(m) for m in monthly["year_month"]]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=monthly["total_spent"],
            name="Monthly total",
            marker={"color": ACCENT},
            hovertemplate="%{x}: R$ %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=monthly["rolling_avg"],
            name="3-month average",
            mode="lines",
            line={"color": AVERAGE, "dash": "dash", "width": 2},
            hovertemplate="3-month avg: R$ %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(plotly_layout(height=340, showlegend=True, legend=LEGEND_TOP))
    return fig


def recurrence_lines(curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    scopes = ["Total"] + sorted(s for s in curve["scope"].unique() if s != "Total")
    for scope in scopes:
        grp = curve[curve["scope"] == scope]
        if grp.empty:
            continue
        is_total = scope == "Total"
        fig.add_trace(
            go.Scatter(
                x=grp["days"],
                y=grp["cumulative_pct"],
                mode="lines",
                name="All markets" if is_total else str(scope),
                line={
                    "color": market_color(scope),
                    "width": 3 if is_total else 2,
                    "dash": "solid" if is_total else "dot",
                    "shape": "hv",
                },
                hovertemplate="%{fullData.name}: %{y:.0%} within %{x} days<extra></extra>",
            )
        )
    fig.add_hline(y=0.5, line={"dash": "dash", "color": MUTED, "width": 1})
    fig.update_layout(
        plotly_layout(
            height=340,
            showlegend=True,
            legend=LEGEND_TOP,
            yaxis={
                "showgrid": True,
                "gridcolor": "#262B36",
                "zeroline": False,
                "title": None,
                "tickformat": ".0%",
                "range": [0, 1.02],
            },
            xaxis={
                "showgrid": False,
                "zeroline": False,
                "title": {"text": "Days since previous purchase", "font": {"size": 11}},
            },
        )
    )
    return fig
