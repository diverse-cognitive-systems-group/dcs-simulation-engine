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
    download_items: list[tuple[str, str]] | None = None,
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
    artifacts:
        Mapping of artifact key → {b64, filename, mime} for downloadable files.
    download_items:
        List of (label, key) pairs rendered as dropdown menu items. Each key
        must match an entry in *artifacts*. Defaults to the standard
        raw_results / run_config pair.

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

    _download_items = download_items if download_items is not None else [
        ("Raw Results (.zip)", "raw_results"),
        ("Run Config (.yml)", "run_config"),
    ]

    return template.render(
        title=title,
        sections=sections,
        generated_at=generated_at,
        artifacts_json=json.dumps(artifacts or {}),
        download_items=_download_items,
    )
