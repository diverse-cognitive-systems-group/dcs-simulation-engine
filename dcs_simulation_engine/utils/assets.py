"""Resolve canonical DCS asset paths for repo (host machine or devcontainer) and installed-package."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dcs_simulation_engine.utils.paths import package_root

AssetMode = Literal["repo", "package"]


@dataclass(frozen=True)
class DCSAssets:
    """Resolved paths to local engine assets."""

    mode: AssetMode
    root: Path
    compose_file: Path
    docker_dir: Path
    run_configs_dir: Path
    default_run_config: Path
    database_seeds_dir: Path
    ui_dist_dir: Path


def resolve_assets(start: Path | None = None) -> DCSAssets:
    """Return repo assets when available, otherwise packaged assets."""
    repo_root = find_repo_root(start)
    if repo_root is not None:
        return _assets_from_root("repo", repo_root)

    package_assets_root = packaged_assets_root()
    if _has_required_package_assets(package_assets_root):
        return _assets_from_root("package", package_assets_root)

    raise FileNotFoundError(
        "DCS assets not found. Expected a repository checkout with compose.yml/docker/database_seeds, "
        f"or packaged assets at {package_assets_root}."
    )


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk upward from start looking for a DCS repository checkout."""
    candidate = (start or Path.cwd()).resolve()
    for path in [candidate, *candidate.parents]:
        if _has_required_assets(path) and (path / "pyproject.toml").is_file() and (path / "dcs_simulation_engine").is_dir():
            return path
    return None


def packaged_assets_root() -> Path:
    """Return the expected package asset root inside an installed package."""
    return package_root() / "package_assets"


def _assets_from_root(mode: AssetMode, root: Path) -> DCSAssets:
    root = root.resolve()
    run_configs_dir = root / "examples" / "run_configs"
    return DCSAssets(
        mode=mode,
        root=root,
        compose_file=root / "compose.yml",
        docker_dir=root / "docker",
        run_configs_dir=run_configs_dir,
        default_run_config=run_configs_dir / "demo.yml",
        database_seeds_dir=root / "database_seeds",
        ui_dist_dir=_ui_dist_dir(root, mode=mode),
    )


def _has_required_assets(root: Path) -> bool:
    return (
        (root / "compose.yml").is_file()
        and (root / "docker").is_dir()
        and (root / "examples" / "run_configs" / "demo.yml").is_file()
        and (root / "database_seeds").is_dir()
    )


def _has_required_package_assets(root: Path) -> bool:
    return _has_required_assets(root) and (root / "ui_dist" / "index.html").is_file()


def _ui_dist_dir(root: Path, *, mode: AssetMode) -> Path:
    if mode == "package":
        return root / "ui_dist"
    return root / "ui" / "dist"
