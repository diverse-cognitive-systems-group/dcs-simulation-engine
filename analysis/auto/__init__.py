"""Auto-analysis pipeline.

Entry point:

    from analysis.auto import run_analysis
    html = run_analysis(data, title="My Study")

Or via CLI:

    python -m analysis.auto <results_dir> [--title "..."] [--open]
"""

import base64
from pathlib import Path

from analysis.auto.rendering.html_builder import build_html
from analysis.auto.sections import (
    form_responses,
    metadata,
    player_feedback,
    player_performance,
    runs_overview,
    system_errors,
    system_performance,
    transcripts,
)
from analysis.common.loader import AnalysisData

# Registry of sections in display order: (anchor_slug, display_title, module, kind)
# kind:
#   "top"   — full section with <h2> heading, rendered in main content
#   "sub"   — indented sidebar entry, rendered in main content (same as top but visually nested)
#   "group" — sidebar label only (no anchor, no content); anchor and module are None
SECTIONS = [
    ("metadata",            "Metadata",       metadata,            "top"),
    ("runs-overview",       "Overview",       runs_overview,       "top"),
    (None,                  "Player",         None,                "group"),
    ("player-performance",  "Performance",    player_performance,  "sub"),
    ("player-feedback",     "Feedback",       player_feedback,     "sub"),
    ("form-responses",      "Form Responses", form_responses,      "sub"),
    (None,                  "System",         None,                "group"),
    ("system-performance",  "Performance",    system_performance,  "sub"),
    ("system-errors",       "Errors",         system_errors,       "sub"),
    ("transcripts",         "Transcripts",    transcripts,         "top"),
]


def _read_b64(path: Path) -> str | None:
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return None


def run_analysis(data: AnalysisData, title: str = "Results Report") -> str:
    """Render all registered sections and return the complete HTML string."""
    rendered: list[tuple[str | None, str, str, str]] = []
    for anchor, section_title, module, kind in SECTIONS:
        if kind == "group":
            rendered.append((None, section_title, "", "group"))
            continue
        try:
            fragment = module.render(data)
        except Exception as exc:
            fragment = (
                f'<div class="alert alert-danger">'
                f"<strong>Error rendering &ldquo;{section_title}&rdquo;:</strong> "
                f"{exc}"
                f"</div>"
            )
        rendered.append((anchor, section_title, fragment, kind))

    raw_results_path = data.results_dir.with_suffix(".zip")
    run_config_path = data.results_dir / "run_config.yml"
    artifacts = {
        "raw_results": {"b64": _read_b64(raw_results_path), "filename": raw_results_path.name, "mime": "application/zip"},
        "run_config": {"b64": _read_b64(run_config_path), "filename": "run_config.yml", "mime": "text/yaml"},
    }

    return build_html(rendered, title=title, artifacts=artifacts)
