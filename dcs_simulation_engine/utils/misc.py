"""Miscellaneous utility functions for DCS Simulation Engine."""

import json
from typing import Any, Dict


def parse_kv(pairs: list[str]) -> Dict[str, Any]:
    """Parse key=value tokens into a dict. Values accept JSON."""
    out: Dict[str, Any] = {}
    for token in pairs:
        if "=" not in token:
            raise ValueError(f"bad field (expected key=value): {token!r}")
        k, v = token.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out
