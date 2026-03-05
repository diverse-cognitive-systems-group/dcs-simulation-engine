"""Fixtures for core games."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

YAML_EXTS = (".yaml", ".yaml")
GAMES_DIR = Path(__file__).parent.parent / "games"


@pytest.fixture
def echo_game(
    write_yaml: Callable[[Path, str], Path], tmp_path_factory: pytest.TempPathFactory
) -> SimpleNamespace:
    """Return a yaml file of a simple echo game."""
    base = tmp_path_factory.mktemp("cfg_minimal")
    echo_yaml = """
    graph_config:
      name: echo_graph
      description: A single echo node graph.
      nodes:
        - name: echo
          kind: custom
          provider: openrouter
          model: deepseek/deepseek-chat-v3-0324
          system_prompt_template: |
            Echo back the input string provided.

            {% if len(messages) > 0 %}
            Input: {{ message[-1] }}
            {% else %}
            Input: null 
            {% endif %}       

            Output format: {
              "message": str                   # echo of the input
            }
      edges:
        - from: __START__
          to: echo
        - from: echo
          to: __END__
    """
    echo_path = base / "echo.yaml"
    write_yaml(echo_path, echo_yaml)
    return SimpleNamespace(path=echo_path)


@pytest.fixture(scope="module")
def games_fpaths() -> list[Path]:
    """Return all yaml/yaml files under games/ sorted."""
    files = [
        p for p in GAMES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in YAML_EXTS
    ]
    return sorted(files)
