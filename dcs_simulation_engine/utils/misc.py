"""Miscellaneous utility functions for DCS Simulation Engine."""

import json
import pickle
from typing import Any, Dict

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
