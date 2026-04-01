"""Auto-analysis pipeline.

Entry point:

    from dcs_utils.analysis.auto import run_analysis
    html = run_analysis(data, title="My Study")

Or via CLI:

    python -m dcs_utils.analysis.auto <results_dir> [--title "..."] [--open]
"""

from __future__ import annotations

from dcs_utils.analysis.auto.rendering.html_builder import build_html
from dcs_utils.analysis.auto.sections import (
    logs_table,
    metadata,
    player_engagement,
    player_feedback,
    player_performance,
    players_table,
    runs_overview,
    system_errors,
    system_performance,
    transcripts,
)
from dcs_utils.analysis.common.loader import AnalysisData

# Registry of sections in display order: (anchor_slug, display_title, module)
SECTIONS = [
    ("metadata",            "Metadata Summary",    metadata),
    ("runs-overview",       "Runs Overview",       runs_overview),
    ("system-performance",  "System Performance",  system_performance),
    ("player-engagement",   "Player Engagement",   player_engagement),
    ("player-feedback",     "Player Feedback",     player_feedback),
    ("player-performance",  "Player Performance",  player_performance),
    ("transcripts",         "Transcripts",         transcripts),
    ("players",             "Players",             players_table),
    ("logs",                "Logs",                logs_table),
    ("system-errors",       "System Errors",       system_errors),
]


def run_analysis(data: AnalysisData, title: str = "DCS Run Analysis Report") -> str:
    """Render all registered sections and return the complete HTML string."""
    rendered: list[tuple[str, str, str]] = []
    for anchor, section_title, module in SECTIONS:
        try:
            fragment = module.render(data)
        except Exception as exc:
            fragment = (
                f'<div class="alert alert-danger">'
                f"<strong>Error rendering &ldquo;{section_title}&rdquo;:</strong> "
                f"{exc}"
                f"</div>"
            )
        rendered.append((anchor, section_title, fragment))

    return build_html(rendered, title=title)
