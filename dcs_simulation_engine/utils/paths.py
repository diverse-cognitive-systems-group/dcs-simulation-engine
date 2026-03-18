"""Path utilities."""

from importlib import resources
from pathlib import Path


def package_root() -> Path:
    """Returns the root path of the dcs_simulation_engine package."""
    return Path(str(resources.files("dcs_simulation_engine")))


def package_games_dir() -> Path:
    """Returns the path to the package's games directory."""
    return package_root().parent / "games"
