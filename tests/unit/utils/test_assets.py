"""Tests for DCS asset path resolution."""

from pathlib import Path

import pytest
from dcs_simulation_engine.utils import assets


def _write(path: Path, text: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_asset_root(root: Path, *, repo: bool = False, packaged_ui: bool = False) -> Path:
    _write(root / "compose.yml", "services: {}\n")
    _write(root / "docker" / "api.dockerfile")
    _write(root / "docker" / "db.dockerfile")
    _write(root / "docker" / "ui.dockerfile")
    _write(root / "examples" / "run_configs" / "demo.yml", "name: demo\n")
    _write(root / "database_seeds" / "dev" / "characters.json", "[]\n")
    if packaged_ui:
        _write(root / "ui_dist" / "index.html", "<div></div>\n")
    else:
        _write(root / "ui" / "dist" / "index.html", "<div></div>\n")
    if repo:
        _write(root / "pyproject.toml", "[project]\nname = 'dcs-simulation-engine'\n")
        (root / "dcs_simulation_engine").mkdir()
    return root


@pytest.mark.unit
def test_resolve_assets_prefers_repo_checkout_from_nested_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repo checkouts should resolve from nested working directories."""
    repo_root = _make_asset_root(tmp_path / "repo", repo=True)
    nested = repo_root / "dcs_simulation_engine" / "cli"
    nested.mkdir(parents=True)
    package_root = tmp_path / "site-packages" / "dcs_simulation_engine"
    _make_asset_root(package_root / "package_assets", packaged_ui=True)
    monkeypatch.setattr(assets, "package_root", lambda: package_root)

    resolved = assets.resolve_assets(nested)

    assert resolved.mode == "repo"
    assert resolved.root == repo_root.resolve()
    assert resolved.compose_file == repo_root / "compose.yml"
    assert resolved.docker_dir == repo_root / "docker"
    assert resolved.run_configs_dir == repo_root / "examples" / "run_configs"
    assert resolved.default_run_config == repo_root / "examples" / "run_configs" / "demo.yml"
    assert resolved.database_seeds_dir == repo_root / "database_seeds"
    assert resolved.ui_dist_dir == repo_root / "ui" / "dist"


@pytest.mark.unit
def test_resolve_assets_falls_back_to_packaged_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Installed package assets should resolve when no repo checkout is nearby."""
    package_root = tmp_path / "site-packages" / "dcs_simulation_engine"
    package_assets_root = _make_asset_root(package_root / "package_assets", packaged_ui=True)
    monkeypatch.setattr(assets, "package_root", lambda: package_root)

    resolved = assets.resolve_assets(tmp_path / "not-a-repo")

    assert resolved.mode == "package"
    assert resolved.root == package_assets_root.resolve()
    assert resolved.compose_file == package_assets_root / "compose.yml"
    assert resolved.ui_dist_dir == package_assets_root / "ui_dist"


@pytest.mark.unit
def test_find_repo_root_requires_project_markers(tmp_path: Path) -> None:
    """Asset-like directories without repo markers should not count as a checkout."""
    asset_root = _make_asset_root(tmp_path / "looks-like-assets")

    assert assets.find_repo_root(asset_root) is None


@pytest.mark.unit
def test_resolve_assets_fails_when_no_asset_layout_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing repo and package assets should produce an actionable error."""
    package_root = tmp_path / "site-packages" / "dcs_simulation_engine"
    monkeypatch.setattr(assets, "package_root", lambda: package_root)

    with pytest.raises(FileNotFoundError, match="DCS assets not found"):
        assets.resolve_assets(tmp_path / "not-a-repo")
