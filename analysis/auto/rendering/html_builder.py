"""Assemble the final HTML document from rendered section fragments."""



import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def build_html(
    sections: list[tuple[str, str, str, bool]],
    title: str = "Results Report",
    artifacts: dict[str, Any] | None = None,
) -> str:
    """Render the Jinja2 base template with all section fragments.

    Parameters
    ----------
    sections:
        List of (anchor_slug, section_title, html_fragment, is_sub) tuples in
        display order. is_sub=True renders the sidebar entry as an indented
        child of the preceding top-level item.
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
    env.filters["tojson"] = json.dumps
    template = env.get_template("base.html")

    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return template.render(
        title=title,
        sections=sections,
        generated_at=generated_at,
        artifacts_json=json.dumps(artifacts or {}),
    )
