"""Package utils."""

from importlib.metadata import (
    PackageNotFoundError,
    packages_distributions,
    version,
)


def get_package_name() -> str:
    """Get the package name."""
    return (__package__ or __name__).split(".", 1)[0]


def get_package_version() -> str:
    """Get the current version of the package."""
    try:
        pkg = get_package_name()
        dist = packages_distributions()[pkg][0]
        return version(dist)
    except PackageNotFoundError:
        return "0.0.0"
