"""Tests for package asset staging and artifact checks."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.unit
def test_stage_package_assets_copies_required_assets_and_removes_stale_files(tmp_path: Path) -> None:
    """Staging should rebuild the generated package asset tree from canonical assets."""
    stage_package_assets = _load_script("stage_package_assets")

    _write(tmp_path / "compose.yml", "services: {}\n")
    _write(tmp_path / "docker" / "api.dockerfile")
    _write(tmp_path / "docker" / "db.dockerfile")
    _write(tmp_path / "docker" / "ui.dockerfile")
    _write(tmp_path / "docker" / "Caddyfile")
    _write(tmp_path / "examples" / "run_configs" / "demo.yml", "name: demo\n")
    _write(tmp_path / "database_seeds" / "dev" / "characters.json", "[]\n")
    _write(tmp_path / "ui" / "dist" / "index.html", "<div></div>\n")
    _write(tmp_path / "ui" / "dist" / "assets" / "index.js")
    _write(tmp_path / "ui" / "dist" / "assets" / "index.css")

    _write(tmp_path / "dcs_simulation_engine" / "package_assets" / "stale.txt")

    staged_dir = stage_package_assets.stage_package_assets(tmp_path)

    assert staged_dir == tmp_path / "dcs_simulation_engine" / "package_assets"
    assert not (staged_dir / "stale.txt").exists()
    assert (staged_dir / "compose.yml").is_file()
    assert (staged_dir / "docker" / "api.dockerfile").is_file()
    assert (staged_dir / "examples" / "run_configs" / "demo.yml").is_file()
    assert (staged_dir / "database_seeds" / "dev" / "characters.json").is_file()
    assert (staged_dir / "ui_dist" / "index.html").is_file()
    assert (staged_dir / "ui_dist" / "assets" / "index.css").is_file()


@pytest.mark.unit
def test_stage_package_assets_fails_when_ui_dist_is_missing(tmp_path: Path) -> None:
    """The default UI build must exist before staging package assets."""
    stage_package_assets = _load_script("stage_package_assets")

    _write(tmp_path / "compose.yml", "services: {}\n")
    _write(tmp_path / "docker" / "api.dockerfile")
    _write(tmp_path / "examples" / "run_configs" / "demo.yml", "name: demo\n")
    _write(tmp_path / "database_seeds" / "dev" / "characters.json", "[]\n")

    with pytest.raises(FileNotFoundError, match="ui/dist"):
        stage_package_assets.stage_package_assets(tmp_path)


@pytest.mark.unit
def test_package_artifact_check_accepts_wheel_with_required_assets(tmp_path: Path) -> None:
    """Wheel verification should pass when local engine assets are present."""
    check_package_artifact = _load_script("check_package_artifact")
    wheel_path = tmp_path / "dcs_simulation_engine-0.1.0-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path, "w") as wheel:
        for file_name in check_package_artifact.REQUIRED_WHEEL_FILES:
            wheel.writestr(file_name, "asset")
        wheel.writestr("dcs_simulation_engine/package_assets/ui_dist/assets/index.js", "js")
        wheel.writestr("dcs_simulation_engine/package_assets/ui_dist/assets/index.css", "css")

    assert check_package_artifact.package_asset_errors(wheel_path) == []


@pytest.mark.unit
def test_package_artifact_check_reports_missing_ui_assets(tmp_path: Path) -> None:
    """Wheel verification should fail if the built UI assets are incomplete."""
    check_package_artifact = _load_script("check_package_artifact")
    wheel_path = tmp_path / "dcs_simulation_engine-0.1.0-py3-none-any.whl"

    with zipfile.ZipFile(wheel_path, "w") as wheel:
        for file_name in check_package_artifact.REQUIRED_WHEEL_FILES:
            wheel.writestr(file_name, "asset")
        wheel.writestr("dcs_simulation_engine/package_assets/ui_dist/assets/index.js", "js")

    errors = check_package_artifact.package_asset_errors(wheel_path)

    assert "Missing packaged UI CSS asset under package_assets/ui_dist/assets/" in errors
