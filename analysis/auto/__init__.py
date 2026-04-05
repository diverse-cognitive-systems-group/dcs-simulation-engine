"""Auto-analysis pipeline.

Entry point:

    from analysis.auto import run_analysis
    html = run_analysis(data, title="My Study")

Or via CLI:

    python -m analysis.auto <results_dir> [--title "..."] [--open]
"""

import base64
import types
from pathlib import Path

from analysis.auto.rendering.html_builder import build_html
from analysis.auto.sections import (
    coverage_human,
    coverage_nonhuman,
    form_responses,
    metadata,
    player_feedback,
    player_performance,
    runs_overview,
    simulation_quality,
    system_errors,
    system_performance,
    transcripts,
)
from analysis.common.loader import AnalysisData

_TODO_PLACEHOLDER = (
    '<div class="alert alert-warning mt-3" role="alert">'
    "<strong>TODO:</strong> Add your interpretations and results discussion here."
    "</div>"
)

# Adapters: coverage sections use render(repo_root) but default report uses render(data).
# HIDs are scoped to characters that actually appeared in the run.
def _render_pc_coverage(data):
    pc_hids = None
    if not data.runs_df.empty and "pc_hid" in data.runs_df.columns:
        pc_hids = data.runs_df["pc_hid"].dropna().unique().tolist()
    return coverage_human.render(_find_repo_root(), hids_filter=pc_hids or None)


def _render_npc_coverage(data):
    npc_hids = None
    if not data.runs_df.empty and "npc_hid" in data.runs_df.columns:
        npc_hids = data.runs_df["npc_hid"].dropna().unique().tolist()
    return coverage_nonhuman.render(_find_repo_root(), hids_filter=npc_hids or None)


_pc_coverage = types.SimpleNamespace(render=_render_pc_coverage)
_npc_coverage = types.SimpleNamespace(render=_render_npc_coverage)

# Registry of sections in display order: (anchor_slug, display_title, module, kind)
# kind:
#   "top"   — full section with <h2> heading, rendered in main content
#   "sub"   — indented sidebar entry, rendered in main content (same as top but visually nested)
#   "group" — sidebar label only (no anchor, no content); anchor and module are None
SECTIONS = [
    ("metadata",            "Metadata",           metadata,            "top"),
    ("runs-overview",       "Overview",           runs_overview,       "top"),
    (None,                  "Player",             None,                "group"),
    ("player-performance",  "Performance",        player_performance,  "sub"),
    ("player-feedback",     "Feedback",           player_feedback,     "sub"),
    ("form-responses",      "Form Responses",     form_responses,      "sub"),
    ("pc-coverage",         "PC Coverage",        _pc_coverage,        "sub"),
    (None,                  "System",             None,                "group"),
    ("system-performance",  "Performance",        system_performance,  "sub"),
    ("system-errors",       "Errors",             system_errors,       "sub"),
    ("sim-quality",         "Simulation Quality", simulation_quality,  "sub"),
    ("npc-coverage",        "NPC Coverage",       _npc_coverage,       "sub"),
    ("transcripts",         "Transcripts",        transcripts,         "top"),
]

DEFAULT_SECTIONS = [s for s in SECTIONS if s[0] != "sim-quality"]

VALID_SECTION_SLUGS: frozenset[str] = frozenset(
    anchor for anchor, _, _, _ in SECTIONS if anchor is not None
)
_DEFAULT_SECTION_SLUGS: frozenset[str] = frozenset(
    anchor for anchor, _, _, _ in DEFAULT_SECTIONS if anchor is not None
)


def resolve_sections(
    only: list[str] | None,
    include: list[str] | None,
    exclude: list[str] | None,
) -> list[tuple]:
    """Return an ordered section list derived from the flag arguments.

    Exactly one of *only*, *include*, *exclude* may be non-None.
    Raises ValueError for invalid slug names or mutual-exclusion violations.
    """
    active = [f for f in (only, include, exclude) if f is not None]
    if len(active) > 1:
        raise ValueError("--only, --include, and --exclude are mutually exclusive.")

    def _validate(slugs: list[str]) -> None:
        unknown = [s for s in slugs if s not in VALID_SECTION_SLUGS]
        if unknown:
            valid = ", ".join(sorted(VALID_SECTION_SLUGS))
            raise ValueError(
                f"unknown section name(s): {', '.join(repr(s) for s in unknown)}. "
                f"Valid: {valid}"
            )

    if only is not None:
        _validate(only)
        candidate = frozenset(only)
    elif include is not None:
        _validate(include)
        candidate = _DEFAULT_SECTION_SLUGS | frozenset(include)
    elif exclude is not None:
        _validate(exclude)
        candidate = _DEFAULT_SECTION_SLUGS - frozenset(exclude)
    else:
        candidate = _DEFAULT_SECTION_SLUGS

    result: list[tuple] = []
    pending_group: tuple | None = None
    for entry in SECTIONS:
        anchor, title, module, kind = entry
        if kind == "group":
            pending_group = entry
            continue
        if anchor in candidate:
            # Only emit a pending group label when a sub-section follows it.
            # Top-level sections (kind="top") are not children of any group.
            if pending_group is not None and kind == "sub":
                result.append(pending_group)
            pending_group = None
            result.append(entry)
    return result


def _read_b64(path: Path) -> str | None:
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return None


def run_analysis(
    data: AnalysisData,
    title: str = "Results Report",
    with_todos: bool = False,
    sections: list | None = None,
) -> str:
    """Render all registered sections and return the complete HTML string."""
    if sections is None:
        sections = SECTIONS
    rendered: list[tuple[str | None, str, str, str]] = []
    for anchor, section_title, module, kind in sections:
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
        if with_todos:
            fragment = fragment + _TODO_PLACEHOLDER
        rendered.append((anchor, section_title, fragment, kind))

    raw_results_path = data.results_dir.with_suffix(".zip")
    run_config_path = data.results_dir / "run_config.yml"
    artifacts = {
        "raw_results": {"b64": _read_b64(raw_results_path), "filename": raw_results_path.name, "mime": "application/zip"},
        "run_config": {"b64": _read_b64(run_config_path), "filename": "run_config.yml", "mime": "text/yaml"},
    }

    return build_html(rendered, title=title, artifacts=artifacts)


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) looking for pyproject.toml + database_seeds/."""
    candidate = (start or Path.cwd()).resolve()
    for p in [candidate, *candidate.parents]:
        if (p / "pyproject.toml").exists() and (p / "database_seeds").exists():
            return p
    # Fallback: analysis/auto/__init__.py → parents[2] = repo root
    return Path(__file__).parents[2]


def run_coverage_report(
    repo_root: Path | None = None,
    hids_filter: list[str] | None = None,
    db: str = "prod",
) -> str:
    """Render the character coverage report and return the complete HTML string.

    Loads character data directly from database_seeds/; does not use AnalysisData.
    """
    import json as _json

    from analysis.auto.sections import (
        coverage_human,
        coverage_metadata,
        coverage_nonhuman,
    )

    root = repo_root or _find_repo_root()

    # For prod, restrict to approved characters from the release manifest.
    _no_approved_chars = False
    if hids_filter is None and db == "prod":
        manifest_path = root / "database_seeds" / "prod" / "release_manifest.json"
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            approved = manifest.get("approved_characters") or []
            if approved:
                hids_filter = approved
            else:
                _no_approved_chars = True
        except OSError:
            _no_approved_chars = True

    if _no_approved_chars:
        placeholder = (
            '<div class="alert alert-warning mt-3" role="alert">'
            "<strong>No production characters approved.</strong> "
            "The release manifest contains no approved characters. "
            "Coverage cannot be generated until characters are approved for production."
            "</div>"
        )
        rendered = [("coverage", "Coverage", placeholder, "top")]
        title = f"Character Coverage Report \u2014 {db}"
        return build_html(rendered, title=title, artifacts={}, download_items=[])

    coverage_sections = [
        ("metadata",       "Metadata",       coverage_metadata,  "top"),
        (None,             "Non-human",      None,               "group"),
        ("dim-coverage",   "Dimensions",     coverage_nonhuman,  "sub"),
        (None,             "Human",          None,               "group"),
        ("hsn-divergence", "HSN Divergence", coverage_human,     "sub"),
    ]

    rendered: list[tuple[str | None, str, str, str]] = []
    for anchor, section_title, module, kind in coverage_sections:
        if kind == "group":
            rendered.append((None, section_title, "", "group"))
            continue
        try:
            fragment = module.render(root, hids_filter=hids_filter, db=db)
        except Exception as exc:
            fragment = (
                f'<div class="alert alert-danger">'
                f"<strong>Error rendering &ldquo;{section_title}&rdquo;:</strong> "
                f"{exc}"
                f"</div>"
            )
        rendered.append((anchor, section_title, fragment, kind))

    dims_path = root / "database_seeds" / "dev" / "character_dimensions.json"
    hsn_path = root / "database_seeds" / "dev" / "hsn_assumptions.json"
    chars_path = root / "database_seeds" / db / "characters.json"

    artifacts = {
        "dimensions": {
            "b64": _read_b64(dims_path),
            "filename": "dimensions.json",
            "mime": "application/json",
        },
        "hsn_assumptions": {
            "b64": _read_b64(hsn_path),
            "filename": "hsn_assumptions.json",
            "mime": "application/json",
        },
        "characters": {
            "b64": _read_b64(chars_path),
            "filename": "characters.json",
            "mime": "application/json",
        },
    }

    download_items = [
        ("dimensions.json", "dimensions"),
        ("hsn_assumptions.json", "hsn_assumptions"),
        ("characters.json", "characters"),
    ]

    title = f"Character Coverage Report \u2014 {db}"
    return build_html(
        rendered,
        title=title,
        artifacts=artifacts,
        download_items=download_items,
    )
