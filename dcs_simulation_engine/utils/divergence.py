"""Utilities for comparing character divergence profiles."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


def _flatten_hsn_values(value: Any, *, prefix: str = "") -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    flattened: dict[str, str] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict) and "value" in item:
            raw = str(item.get("value") or "").strip().lower()
            if raw:
                flattened[path] = raw
            continue
        flattened.update(_flatten_hsn_values(item, prefix=path))
    return flattened


def compute_divergence_score(a: CharacterRecord | None, b: CharacterRecord | None) -> float:
    """Compute a deterministic divergence score from two character HSN profiles."""
    if a is None or b is None:
        return 0.0

    a_values = _flatten_hsn_values(a.data.get("hsn_divergence"))
    b_values = _flatten_hsn_values(b.data.get("hsn_divergence"))
    shared_keys = set(a_values) & set(b_values)
    score = 0.0
    for key in shared_keys:
        left = a_values[key]
        right = b_values[key]
        if left == right:
            continue
        if {left, right} == {"divergent", "normative"}:
            score += 2.0
        else:
            score += 1.0
    return score
