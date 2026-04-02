"""Chart rendering helpers.

plotly_to_html  — Plotly Figure → embeddable <div> string (no bundled JS).
matplotlib_to_base64 — matplotlib Figure → <img src="data:..."> string.
"""



import base64
import io


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
