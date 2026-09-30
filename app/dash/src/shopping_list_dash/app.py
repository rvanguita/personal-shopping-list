"""Dash app factory."""

from pathlib import Path

from dash import Dash

from shopping_list_dash.callbacks import register_callbacks
from shopping_list_dash.data import Loader, cached, load_from_database
from shopping_list_dash.layout import build_layout


def create_app(loader: Loader | None = None) -> Dash:
    """`loader` returns a `DashboardData`; defaults to the MySQL Silver/Bronze layers."""
    loader = cached(loader or load_from_database)
    app = Dash(
        __name__,
        title="Shopping List Intelligence",
        assets_folder=str(Path(__file__).parent / "assets"),
        suppress_callback_exceptions=True,
    )
    app.layout = lambda: build_layout(loader())
    register_callbacks(app, loader)
    return app


def main() -> None:
    create_app().run(host="0.0.0.0", port=8050, debug=False)
