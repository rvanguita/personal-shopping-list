"""Callbacks: thin wrappers around pure functions that tests can call directly."""

from dash import Dash, Input, Output, dcc, no_update

from shopping_list_dash import layout, views
from shopping_list_dash.data import Loader


def render_tab(data: views.DashboardData, tab: str):
    renderer = layout.TAB_RENDERERS.get(tab)
    return renderer(data) if renderer else layout.empty_state("Unknown tab.")


def due_csv(data: views.DashboardData) -> str:
    return views.shopping_list_frame(data.products).to_csv(index=False)


def register_callbacks(app: Dash, loader: Loader) -> None:
    @app.callback(Output("tab-content", "children"), Input("tabs", "value"))
    def _render_tab(tab):
        return render_tab(loader(), tab)

    @app.callback(Output("price-detail", "children"), Input("price-product", "value"))
    def _price_detail(product_id):
        return layout.price_detail(loader(), product_id)

    @app.callback(
        Output("download-due", "data"),
        Input("download-due-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _download_due(n_clicks):
        if not n_clicks:
            return no_update
        return dcc.send_string(due_csv(loader()), "shopping_list_due.csv")
