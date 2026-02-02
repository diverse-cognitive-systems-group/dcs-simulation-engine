"""CLI helper functions."""

from importlib.metadata import (
    packages_distributions,
    version,
)


def get_version() -> str:
    """Get the current version of the package."""
    try:
        pkg = (__package__ or __name__).split(".", 1)[0]
        dist = packages_distributions()[pkg][0]
        return version(dist)
    except Exception:
        return "0.0.0"
