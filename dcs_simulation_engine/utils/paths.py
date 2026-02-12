"""Path utilities."""

from importlib import resources
from pathlib import Path

from dcs_simulation_engine.utils.package import get_package_name


def package_root() -> Path:
    """Returns the root path of the dcs_simulation_engine package."""
    pkg_name = get_package_name()
    return Path(str(resources.files(pkg_name)))


def package_games_dir() -> Path:
    """Returns the path to the package's games directory."""
    return package_root() / "games"
