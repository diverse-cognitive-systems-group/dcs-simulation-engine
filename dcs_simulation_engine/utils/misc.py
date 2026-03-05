"""Miscellaneous utility functions for DCS Simulation Engine."""

import json
import pickle
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
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


def fmt_uptime(dt: Optional[datetime]) -> str:
    """Return human-friendly uptime like '5m', '2h', '3d'."""
    if not dt:
        return "—"

    delta = datetime.now(timezone.utc) - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def validate_port(port: int) -> bool:
    """Validate if the given port number is valid."""
    if not (1 <= port <= 65535):
        return False
    return True


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


def get_version() -> str:
    """Get the current package version."""
    try:
        return version("dcs-simulation-engine")  # your package name from pyproject
    except PackageNotFoundError:
        return "0.0.0"  # fallback for editable/local use


def byte_size_json(obj: Any) -> int:
    """Return the size in bytes of the JSON-encoded object."""
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def byte_size_pickle(obj: Any) -> int:
    """Return the size in bytes of the pickled object."""
    return len(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


# def make_human_readable_values(data: dict[str, Any]) -> dict[str, str]:
#     """Recursively clean and humanize all values in a dict.

#     Without changing the overall structure (lists stay lists,
#     dicts stay dicts).
#     """
#     if isinstance(data, dict):
#         return {k: make_human_readable_values(v) for k, v in data.items()}

#     if isinstance(data, list):
#         return [make_human_readable_values(v) for v in data]

#     # primitives → return cleaned version
#     if isinstance(data, str):
#         return data.strip()

#     return data


def _value_to_markdown(value: Any, depth: int = 0) -> str:
    """Recursively convert any value to a markdown string."""
    indent = "  " * depth

    # Scalars
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)

    # Lists -> bullet lists
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            item_md = _value_to_markdown(item, depth + 1)
            item_lines = item_md.splitlines() or [""]
            # First line with "- "
            first = f"{indent}- {item_lines[0]}"
            lines.append(first)
            # Subsequent lines indented under the bullet
            for extra in item_lines[1:]:
                lines.append(f"{indent}  {extra}")
        return "\n".join(lines)

    # Dicts -> bullets of key/value; nested handled recursively
    if isinstance(value, dict):
        lines: list[str] = []
        for k, v in value.items():
            v_md = _value_to_markdown(v, depth + 1)
            v_lines = v_md.splitlines() if v_md else []

            if not v_lines:
                # Just the key
                lines.append(f"{indent}- **{k}**")
            elif len(v_lines) == 1:
                # Single-line value goes inline
                lines.append(f"{indent}- **{k}**: {v_lines[0]}")
            else:
                # Multi-line value goes on following lines, indented
                lines.append(f"{indent}- **{k}**")
                for line in v_lines:
                    lines.append(f"{indent}  {line}")
        return "\n".join(lines)

    # Fallback
    return str(value)


def dict_to_markdown(doc: Dict[str, Any]) -> Dict[str, str]:
    """Clean and convert all values in a dict to nice markdown.

    - Handles nested dicts/lists.
    - Every value becomes a markdown string.
    """
    return {k: _value_to_markdown(v).rstrip() for k, v in doc.items()}
