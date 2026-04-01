"""Assemble the final HTML document from rendered section fragments."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def build_html(
    sections: list[tuple[str, str, str]],
    title: str = "DCS Analysis Report",
) -> str:
    """Render the Jinja2 base template with all section fragments.

    Parameters
    ----------
    sections:
        List of (anchor_slug, section_title, html_fragment) tuples in display order.
    title:
        Report title shown in <h1> and <title>.

    Returns
    -------
    str
        Complete, self-contained HTML document as a string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,  # sections contain trusted HTML we generated
    )
    template = env.get_template("base.html")

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return template.render(
        title=title,
        sections=sections,
        generated_at=generated_at,
    )
