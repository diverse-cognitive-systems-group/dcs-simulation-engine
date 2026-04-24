"""Helpers for character filters that inspect HSN divergence data."""

from typing import Any


def section_has_non_normative_assumption(section: Any) -> bool:
    """Return True when a section contains at least one non-normative assumption."""
    if not isinstance(section, dict):
        return False

    for assumption in section.values():
        if not isinstance(assumption, dict):
            continue
        value = assumption.get("value")
        if value is not None and value != "normative":
            return True
    return False


def has_any_non_normative_hsn_divergence(hsn_divergence: Any) -> bool:
    """Return True when any HSN divergence section contains a non-normative assumption."""
    if not isinstance(hsn_divergence, dict):
        return False
    return any(section_has_non_normative_assumption(section) for section in hsn_divergence.values())
