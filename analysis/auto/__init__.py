"""Auto-analysis pipeline.

Entry point:

    from analysis.auto import run_analysis
    html = run_analysis(data, title="My Study")

Or via CLI:

    python -m analysis.auto <results_dir> [--title "..."] [--open]
"""

from __future__ import annotations

from analysis.auto.rendering.html_builder import build_html
from analysis.auto.sections import (
    metadata,
    player_feedback,
    player_performance,
    runs_overview,
    system_performance,
    transcripts,
)
from analysis.common.loader import AnalysisData

# Registry of sections in display order: (anchor_slug, display_title, module)
SECTIONS = [
    ("metadata",            "Metadata",            metadata),
    ("runs-overview",       "Overview",       runs_overview),
    ("system-performance",  "System Performance",  system_performance),
    ("player-feedback",     "Player Feedback",     player_feedback),
    ("player-performance",  "Player Performance",  player_performance),
    ("transcripts",         "Transcripts",         transcripts),
]


def run_analysis(data: AnalysisData, title: str = "Results Report") -> str:
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
