"""Chart rendering helpers.

plotly_to_html  — Plotly Figure → embeddable <div> string (no bundled JS).
matplotlib_to_base64 — matplotlib Figure → <img src="data:..."> string.
"""

import base64
import io


def short_player_id(value, *, suffix_chars: int = 8) -> str:
    """Display long player IDs by keeping the distinguishing suffix."""
    if value is None:
        return ""

    try:
        from pandas import isna

        if isna(value):
            return ""
    except Exception:
        pass

    try:
        if value != value:
            return ""
    except Exception:
        pass

    text = str(value)
    if len(text) <= suffix_chars + 3:
        return text
    return f"...{text[-suffix_chars:]}"


def add_short_player_id_column(df, *, source: str = "player_id", target: str = "player_label"):
    """Return a copy of *df* with a shortened player-ID display column."""
    if source not in df.columns:
        return df.copy()

    display = df.copy()
    display[target] = display[source].map(short_player_id)
    return display


def use_integer_ticks(fig, *, x: bool = False, y: bool = False):
    """Force whole-number tick labels on numeric Plotly axes."""
    axis_options = {"dtick": 1, "tickformat": ",d"}
    if x:
        fig.update_xaxes(**axis_options)
    if y:
        fig.update_yaxes(**axis_options)
    return fig


def plotly_to_html(fig, div_id: str | None = None) -> str:
    """Return an embeddable HTML div for *fig*.

    Requires Plotly to be loaded from CDN in the page <head>.
    """
    import plotly.io as pio

    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"responsive": True},
    )


def matplotlib_to_base64(fig) -> str:
    """Return an <img> tag with the figure embedded as a base64 PNG."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{encoded}" class="img-fluid" alt="chart">'
