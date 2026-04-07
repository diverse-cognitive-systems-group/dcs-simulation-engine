"""Release policy utilities for the DCS character production pipeline.

Loads the character-release-policy.yml and uses it to compute which characters
in prod/characters.json are approved for release, then writes the manifest.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dcs_simulation_engine.utils.fingerprint import compute_character_evaluation_fingerprint

# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------


def load_policy(path: Path) -> dict[str, Any]:
    """Load and return the character release policy from a YAML file."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Approval computation
# ---------------------------------------------------------------------------


def compute_approved_characters(
    policy: dict[str, Any],
    evaluations: list[dict[str, Any]],
    prod_chars_by_hid: dict[str, dict[str, Any]],
) -> list[str]:
    """Return sorted list of character HIDs approved under *policy*.

    Parameters
    ----------
    policy:
        Parsed policy dict (from :func:`load_policy`).
    evaluations:
        List of evaluation dicts from ``character_evaluations.json``.
    prod_chars_by_hid:
        Mapping of ``hid → character doc`` for all characters in prod.

    A character is approved if it has at least one evaluation that passes
    ALL policy criteria:
    - ``scores.icf >= criteria.min_icf_score``
    - (if ``require_current_fingerprint``) evaluation fingerprint matches
      the fingerprint computed from the current character doc, model, and
      updater prompt template.
    """
    from analysis.auto.publish import build_char_record_from_doc

    criteria = policy.get("criteria", {})
    min_icf: float = criteria.get("min_icf_score", 0.0)
    min_scenario_coverage: float = criteria.get("min_scenario_coverage_score", 0.0)
    require_fp: bool = criteria.get("require_current_fingerprint", False)

    # Pre-index evaluations by character_hid for fast lookup
    evals_by_hid: dict[str, list[dict]] = {}
    for ev in evaluations:
        hid = ev.get("character_hid", "")
        evals_by_hid.setdefault(hid, []).append(ev)

    approved: list[str] = []
    for hid, char_doc in prod_chars_by_hid.items():
        char_evals = evals_by_hid.get(hid, [])
        if not char_evals:
            continue

        current_fp: str | None = None
        if require_fp:
            try:
                record = build_char_record_from_doc(char_doc)
                current_fp = compute_character_evaluation_fingerprint(record)
            except Exception:
                continue  # can't fingerprint → skip

        for ev in char_evals:
            scores = ev.get("scores", {})
            icf = scores.get("icf", 0.0)
            if icf < min_icf:
                continue
            if min_scenario_coverage > 0 and scores.get("scenario_coverage", 0.0) < min_scenario_coverage:
                continue
            if require_fp and current_fp is not None:
                if ev.get("fingerprint", "") != current_fp:
                    continue
            # Passed all criteria
            approved.append(hid)
            break

    return sorted(approved)


# ---------------------------------------------------------------------------
# Manifest writing
# ---------------------------------------------------------------------------

_ENGINE_VERSION = "dcs-se@0.1.0"


def write_manifest(
    path: Path,
    approved_hids: list[str],
    policy_version: str,
) -> None:
    """Write the release manifest JSON to *path*.

    Creates parent directories if they don't exist.
    """
    manifest = {
        "policy_version": policy_version,
        "engine_version": _ENGINE_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "approved_characters": approved_hids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
