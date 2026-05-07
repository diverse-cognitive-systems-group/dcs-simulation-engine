"""Stage generated package assets before building distributions."""

import shutil
from pathlib import Path

PACKAGE_ASSETS_DIR = Path("dcs_simulation_engine/package_assets")


def stage_package_assets(repo_root: Path | None = None) -> Path:
    """Copy canonical repo assets into the Python package data tree."""
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    target = root / PACKAGE_ASSETS_DIR

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    _copy_file(root / "compose.yml", target / "compose.yml")
    _copy_tree(root / "docker", target / "docker")
    _copy_tree(root / "examples" / "run_configs", target / "examples" / "run_configs")
    _copy_tree(root / "database_seeds", target / "database_seeds")
    _copy_tree(root / "ui" / "dist", target / "ui_dist")
    return target


def _copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required package asset file not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required package asset directory not found: {source}")
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


if __name__ == "__main__":
    staged_dir = stage_package_assets()
    print(f"Staged package assets at {staged_dir}")
