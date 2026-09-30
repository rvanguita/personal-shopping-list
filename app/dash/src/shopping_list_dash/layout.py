"""Layout builders. They only arrange components; numbers come from `views`."""

from collections.abc import Callable

import pandas as pd
from dash import dcc, html

from shopping_list.analytics import market_color
from shopping_list_dash import figures, views
from shopping_list_dash import formatting as fmt
from shopping_list_dash.theme import GRAPH_CONFIG

TABS = [
    ("list", "Shopping list"),
    ("prices", "Prices"),
    ("markets", "Markets"),
    ("trends", "Trends"),
]

EMPTY_MESSAGE = (
    "No data yet — import receipts in the Streamlit app to populate this view."
)


# -----------------------------------------------------------------------------
# Building blocks
# -----------------------------------------------------------------------------


def empty_state(message: str = EMPTY_MESSAGE) -> html.Div:
    return html.Div(message, className="empty")


def card(
    title: str, body, subtitle: str | None = None, class_name: str = ""
) -> html.Section:
    header = [html.H3(title, className="card-title")]
    if subtitle:
        header.append(html.P(subtitle, className="card-subtitle"))
    return html.Section(
        [html.Header(header), body], className=f"card {class_name}".strip()
    )


def graph(fig) -> dcc.Graph:
    return dcc.Graph(figure=fig, config=GRAPH_CONFIG, className="graph")


def kpi_card(kpi: views.Kpi) -> html.Div:
    return html.Div(
        [
            html.Div(kpi.label, className="kpi-label"),
            html.Div(kpi.value, className="kpi-value"),
            html.Div(kpi.note, className=f"kpi-note tone-{kpi.tone}"),
        ],
        className="kpi",
        title=kpi.help,
    )


def dot(color: str) -> html.Span:
    return html.Span(className="dot", style={"backgroundColor": color})


def table(
    df: pd.DataFrame,
    columns: list[tuple[str, str, Callable | None]],
    numeric: set[str] = frozenset(),
    max_rows: int = 15,
) -> html.Div:
    """Simple dark table. `columns` = (key, header, formatter)."""
    head = html.Thead(
        html.Tr(
            [
                html.Th(label, className="num" if key in numeric else None)
                for key, label, _ in columns
            ]
        )
    )
    rows = []
    for _, row in df.head(max_rows).iterrows():
        cells = []
        for key, _, formatter in columns:
            value = row[key]
            content = formatter(value) if formatter else value
            cells.append(html.Td(content, className="num" if key in numeric else None))
        rows.append(html.Tr(cells))
    footer = (
        html.P(f"Showing {max_rows} of {len(df)} rows.", className="table-note")
        if len(df) > max_rows
        else None
    )
    return html.Div(
        [html.Table([head, html.Tbody(rows)], className="table"), footer],
        className="table-wrap",
    )


def market_label(name: str) -> html.Span:
    return html.Span([dot(market_color(name)), str(name)])


def grid(*children, cols: int = 2) -> html.Div:
    return html.Div(list(children), className=f"grid grid-{cols}")


# -----------------------------------------------------------------------------
# Page
# -----------------------------------------------------------------------------


def build_layout(data: views.DashboardData) -> html.Div:
    kpis = views.build_kpis(data, fmt)
    banner = html.Div(data.error, className="banner") if data.error else None
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.H1("Shopping List Intelligence"),
                            html.P(
                                "Grocery spending, prices and restocking insights from your receipts.",
                                className="subtitle",
                            ),
                        ]
                    ),
                    html.Div(
                        f"Latest purchase {fmt.iso_date(views.latest_purchase(data))}",
                        className="updated",
                    ),
                ],
                className="page-header",
            ),
            banner,
            html.Div([kpi_card(k) for k in kpis], className="kpis") if kpis else None,
            dcc.Tabs(
                id="tabs",
                value=TABS[0][0],
                children=[
                    dcc.Tab(
                        label=label,
                        value=value,
                        className="tab",
                        selected_className="tab--selected",
                    )
                    for value, label in TABS
                ],
                className="tabs",
                parent_className="tabs-parent",
            ),
            dcc.Loading(
                html.Div(id="tab-content", className="tab-content"),
                type="dot",
                color="#4C9BE8",
            ),
            dcc.Download(id="download-due"),
        ],
        className="page",
    )


# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------


def shopping_list_tab(data: views.DashboardData) -> html.Div:
    if data.products.empty:
        return empty_state()
    due = views.shopping_list_frame(data.products)
    upcoming = views.upcoming_frame(data.products)

    if due.empty:
        due_body = empty_state(
            "Nothing is overdue — every product is within its usual interval."
        )
        chart_body = empty_state("No overdue products.")
    else:
        due_body = html.Div(
            [
                table(
                    due,
                    [
                        ("product_id", "Product", None),
                        ("last_purchase_date", "Last bought", fmt.iso_date),
                        ("days_last_purchase", "Days since", fmt.integer),
                        ("avg_days_purchase", "Usual interval", fmt.days),
                        ("avg_product_price", "Avg price", fmt.brl),
                    ],
                    numeric={
                        "days_last_purchase",
                        "avg_days_purchase",
                        "avg_product_price",
                    },
                ),
                html.Button("Download CSV", id="download-due-btn", className="button"),
            ]
        )
        chart_body = graph(figures.overdue_bars(due))

    upcoming_body = (
        empty_state("Nothing else is due in the next 7 days.")
        if upcoming.empty
        else table(
            upcoming,
            [("product_id", "Product", None), ("due_in_days", "Due in", fmt.days)],
            numeric={"due_in_days"},
            max_rows=10,
        )
    )

    return html.Div(
        [
            html.P("What should I buy now?", className="question"),
            grid(
                card(
                    f"Due now ({len(due)})",
                    due_body,
                    "Days since the last purchase exceed the product's usual interval.",
                ),
                html.Div(
                    [
                        card(
                            "Most overdue", chart_body, "Days past the usual interval."
                        ),
                        card("Coming up", upcoming_body, "Due within the next 7 days."),
                    ],
                    className="stack",
                ),
            ),
        ]
    )


def prices_tab(data: views.DashboardData) -> html.Div:
    options = views.product_options(data.products, data.bronze)
    if not options:
        return empty_state()
    alerts = views.price_alerts(data.bronze)
    alerts_body = (
        empty_state(
            "No product's last price rose more than 15% above its prior average."
        )
        if alerts.empty
        else table(
            alerts,
            [
                ("product_id", "Product", None),
                ("last_price", "Last price", fmt.brl),
                ("prior_avg_price", "Prior avg", fmt.brl),
                ("variation_pct", "Change", fmt.pct),
                ("last_purchase_date", "Date", fmt.iso_date),
            ],
            numeric={"last_price", "prior_avg_price", "variation_pct"},
        )
    )
    return html.Div(
        [
            html.P("How are prices moving?", className="question"),
            html.Div(
                [
                    html.Label("Product", htmlFor="price-product"),
                    dcc.Dropdown(
                        id="price-product",
                        options=options,
                        value=options[0],
                        clearable=False,
                        labels={
                            "search": "Search",
                            "no_options_found": "No products found",
                        },
                    ),
                ],
                className="filter",
            ),
            html.Div(id="price-detail"),
            card(
                "Price alerts",
                alerts_body,
                "Last price paid more than 15% above the product's prior average.",
            ),
        ]
    )


def price_detail(data: views.DashboardData, product_id: str | None) -> html.Div:
    history = views.price_history(data.bronze, product_id)
    summary = views.price_summary(data.products, product_id)
    stats = []
    if summary:
        stats = [
            views.Kpi(
                "Average price",
                fmt.brl(summary["avg_product_price"]),
                f"{fmt.integer(summary['total_purchases'])} purchases",
                "",
            ),
            views.Kpi(
                "Lowest",
                fmt.brl(summary["min_product_price"]),
                "minimum price paid",
                "",
            ),
            views.Kpi(
                "Highest",
                fmt.brl(summary["max_product_price"]),
                "maximum price paid",
                "",
            ),
            views.Kpi(
                "Usual interval",
                fmt.days(summary["avg_days_purchase"]),
                f"last bought {fmt.days(summary['days_last_purchase'])} ago",
                "",
            ),
        ]
    chart = (
        empty_state("No purchases recorded for this product.")
        if history.empty
        else graph(figures.price_history_lines(history))
    )
    return html.Div(
        [
            html.Div([kpi_card(k) for k in stats], className="kpis kpis-compact")
            if stats
            else None,
            card(
                f"Price paid — {product_id}",
                chart,
                "Line total per purchase, colored by market.",
            ),
        ]
    )


def markets_tab(data: views.DashboardData) -> html.Div:
    markets = views.markets_frame(data.markets)
    if markets.empty:
        return empty_state()
    return html.Div(
        [
            html.P("Where do I spend my money?", className="question"),
            grid(
                card(
                    "Total spent by market",
                    graph(figures.market_spend_bars(markets)),
                    "Share of all spending.",
                ),
                card(
                    "Average ticket",
                    graph(figures.market_ticket_bars(markets)),
                    "Spent per shopping trip.",
                ),
            ),
            card(
                "Market details",
                table(
                    markets,
                    [
                        ("market_id", "Market", market_label),
                        ("visit_count", "Visits", fmt.integer),
                        ("total_spent", "Total spent", fmt.brl),
                        ("avg_ticket", "Avg ticket", fmt.brl),
                        ("share", "Share", lambda v: fmt.pct(v, signed=False)),
                        ("last_visit", "Last visit", fmt.iso_date),
                    ],
                    numeric={"visit_count", "total_spent", "avg_ticket", "share"},
                ),
            ),
        ]
    )


def trends_tab(data: views.DashboardData) -> html.Div:
    monthly = views.monthly_frame(data.monthly)
    if monthly.empty:
        return empty_state()
    curve = views.recurrence_frame(data.bronze)
    median = views.median_repurchase_days(curve)
    curve_body = (
        empty_state("Not enough repeat purchases to draw the curve yet.")
        if curve.empty
        else graph(figures.recurrence_lines(curve))
    )
    curve_subtitle = (
        "Share of repurchases that happen within N days of the previous one."
    )
    if median is not None:
        curve_subtitle += f" Half happen within {fmt.days(median)}."
    return html.Div(
        [
            html.P("How is my spending evolving?", className="question"),
            grid(
                card(
                    "Monthly spending",
                    graph(figures.monthly_bars(monthly)),
                    "Bars: month total · dashed: 3-month average.",
                ),
                card("Repurchase curve", curve_body, curve_subtitle),
            ),
            card(
                "Monthly details",
                table(
                    monthly.iloc[::-1],
                    [
                        ("year_month", "Month", fmt.month_label),
                        ("total_spent", "Total spent", fmt.brl),
                        ("item_count", "Items", fmt.integer),
                        ("avg_price", "Avg item price", fmt.brl),
                    ],
                    numeric={"total_spent", "item_count", "avg_price"},
                    max_rows=12,
                ),
            ),
        ]
    )


TAB_RENDERERS = {
    "list": shopping_list_tab,
    "prices": prices_tab,
    "markets": markets_tab,
    "trends": trends_tab,
}
