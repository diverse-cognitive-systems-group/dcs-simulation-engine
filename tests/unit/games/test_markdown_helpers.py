"""Unit tests for markdown formatting helpers used by game command responses."""

import pytest
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown

pytestmark = pytest.mark.unit


def test_format_abilities_markdown_renders_dict_sections_and_bullets() -> None:
    """Structured ability dicts should render as markdown headings with bullets."""
    abilities = {
        "Sensory / Perceptual": [
            "Can perceive visual details.",
            "Cannot process audio without assistance.",
        ],
        "Regulatory": [
            "Typical emotional regulation.",
        ],
    }

    rendered = format_abilities_markdown(abilities)

    assert "### Sensory / Perceptual" in rendered
    assert "- Can perceive visual details." in rendered
    assert "- Cannot process audio without assistance." in rendered
    assert "### Regulatory" in rendered
    assert "- Typical emotional regulation." in rendered
    assert "{'Sensory / Perceptual'" not in rendered


def test_format_abilities_markdown_preserves_plain_strings() -> None:
    """Already-formatted strings should pass through unchanged."""
    rendered = format_abilities_markdown("Already formatted")

    assert rendered == "Already formatted"
