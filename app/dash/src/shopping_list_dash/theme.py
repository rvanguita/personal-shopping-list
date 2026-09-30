"""Dark theme tokens and the shared Plotly layout."""

BG = "#0F1117"
CARD = "#161A23"
BORDER = "#262B36"
TEXT = "#E5E7EB"
MUTED = "#9CA3AF"
ACCENT = "#4C9BE8"
AVERAGE = "#F5B942"
PREVIOUS = "#5B6B80"
BAD = "#F87171"
GOOD = "#34D399"
FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"

SERIES_PALETTE = {ACCENT, AVERAGE, PREVIOUS, BAD, GOOD, MUTED}

LEGEND_TOP = {
    "orientation": "h",
    "x": 0,
    "y": 1.02,
    "yanchor": "bottom",
    "font": {"size": 11},
}

GRAPH_CONFIG = {"displayModeBar": False}


def plotly_layout(height: int = 320, **overrides) -> dict:
    layout = {
        "height": height,
        "margin": {"l": 8, "r": 8, "t": 8, "b": 8},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT, "size": 12, "color": MUTED},
        "showlegend": False,
        "hoverlabel": {"bgcolor": CARD, "bordercolor": BORDER, "font": {"color": TEXT}},
        "separators": ".,",
        "bargap": 0.35,
        "xaxis": {
            "showgrid": False,
            "zeroline": False,
            "linecolor": BORDER,
            "title": None,
        },
        "yaxis": {
            "showgrid": True,
            "gridcolor": BORDER,
            "zeroline": False,
            "title": None,
            "tickprefix": "R$ ",
            "tickformat": ",.0f",
        },
    }
    layout.update(overrides)
    return layout
