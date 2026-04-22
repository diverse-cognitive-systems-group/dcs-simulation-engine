"""Helpers for rendering game content as markdown."""

from typing import Any


def format_abilities_markdown(abilities: Any, *, section_heading_level: int = 3) -> str:
    """Render a character's ability payload as readable markdown."""
    heading_prefix = "#" * max(1, min(section_heading_level, 6))

    if isinstance(abilities, str):
        return abilities

    if isinstance(abilities, list):
        return "\n".join(f"- {str(item).strip()}" for item in abilities if str(item).strip())

    if isinstance(abilities, dict):
        sections: list[str] = []
        for section_name, section_items in abilities.items():
            heading = f"{heading_prefix} {section_name}"
            if isinstance(section_items, list):
                bullets = "\n".join(f"- {str(item).strip()}" for item in section_items if str(item).strip())
                sections.append(f"{heading}\n{bullets}" if bullets else heading)
                continue

            text = str(section_items).strip()
            sections.append(f"{heading}\n{text}" if text else heading)
        return "\n\n".join(section for section in sections if section.strip())

    return str(abilities)


def format_score_markdown(score: dict[str, Any], *, title: str = "Final Score") -> str:
    """Render a scorer payload as readable markdown."""
    if not score:
        return ""

    lines = [f"## {title}"]

    tier = score.get("tier")
    if tier is not None:
        lines.append(f"- Tier: {tier}")

    numeric_score = score.get("score")
    if numeric_score is not None:
        lines.append(f"- Score: {numeric_score}")

    reasoning = str(score.get("reasoning", "")).strip()
    if reasoning:
        lines.extend(["", "### Reasoning", reasoning])

    return "\n".join(lines)
