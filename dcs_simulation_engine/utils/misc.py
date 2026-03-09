"""Miscellaneous utility functions for DCS Simulation Engine."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def fmt_dt(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def parse_iso(s: str) -> datetime:
    """Parse an ISO datetime string, ensuring it's timezone-aware in UTC."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def as_str(d: dict, *keys: str, default: str = "—") -> str:
    """Helper to get a string value from a dict with multiple possible keys."""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return str(v)
    return default


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
