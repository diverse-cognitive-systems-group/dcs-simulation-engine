"""Constants for core module."""

from pathlib import Path

# --- Misc --- #
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# --- I/O --- #
OUTPUT_FPATH: Path = Path("output")
OUTPUT_FPATH.mkdir(parents=True, exist_ok=True)

LOGS_FPATH: Path = Path("logs")
LOGS_FPATH.mkdir(parents=True, exist_ok=True)

_config_fpath: Path = Path("configs")
GRAPH_CONFIG_FPATH: Path = _config_fpath / "graph.config.yml"
GRAPH_CONFIG_FPATH.parent.mkdir(parents=True, exist_ok=True)

# --- Messages for the Simulation Engine (NOT FOR SPECIFIC GAME) --- #
WELCOME_MSG: str = """
# Welcome

This is a textual scenario-based simulation engine that is part of a Georgia
Tech research project. We are studying how different cognitive systems engage
and interact to understand each other—particularly in cases where their
abilities diverge from standard normative assumptions.
"""

USAGE_MSG: str = """
# Instructions

To participate in our research, you'll need to *sign a consent form to receive
an access token*.

With a token, you can start in Benchmarking Mode, which lets us run an
experiment and collect anonymous data about how you engaged with the other
beings you encountered in the simulator.

Alternatively, you can play around in Demo Mode (lower fidelity) without any
data collection.
"""
