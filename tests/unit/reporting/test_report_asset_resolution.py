"""Report commands should use universal asset resolution for seed lookups."""

from pathlib import Path

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.utils import assets
from typer.testing import CliRunner

_RUNNER = CliRunner()
_EXAMPLE_RESULTS = Path(__file__).resolve().parents[2] / "data" / "example_results"


def _write(path: Path, text: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_packaged_report_assets(package_root: Path) -> Path:
    root = package_root / "package_assets"
    _write(root / "compose.yml", "services: {}\n")
    _write(root / "docker" / "api.dockerfile")
    _write(root / "docker" / "db.dockerfile")
    _write(root / "docker" / "ui.dockerfile")
    _write(root / "examples" / "run_configs" / "demo.yml", "name: demo\n")
    _write(root / "ui_dist" / "index.html", "<div></div>\n")
    _write(root / "database_seeds" / "dev" / "characters.json", "[]\n")
    _write(root / "database_seeds" / "dev" / "hsn_assumptions.json", "[]\n")
    _write(
        root / "database_seeds" / "dev" / "character_dimensions.json",
        """
[
  {
    "dimensions": {
      "description": "test",
      "substrate": {"options": ["synthetic"]},
      "size": {"options": ["small"]},
      "origin": {"options": ["built"]},
      "form": {"options": ["embodied"]}
    }
  }
]
""".strip(),
    )
    _write(root / "database_seeds" / "prod" / "characters.json", "[]\n")
    _write(root / "database_seeds" / "prod" / "release_manifest.json", '{"approved_characters": []}\n')
    return root


@pytest.mark.unit
def test_report_coverage_uses_packaged_assets_from_non_repo_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Coverage reports should not require cwd to be a repository checkout."""
    package_root = tmp_path / "site-packages" / "dcs_simulation_engine"
    _make_packaged_report_assets(package_root)
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(assets, "package_root", lambda: package_root)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "dev"])

    assert result.exit_code == 0, result.output
    report_path = workdir / "reports" / "character_coverage_dev.html"
    assert report_path.is_file()
    html = report_path.read_text(encoding="utf-8")
    assert "<html" in html
    assert 'class="alert alert-danger"' not in html


@pytest.mark.unit
def test_report_results_coverage_section_uses_packaged_assets_from_non_repo_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Results reports should resolve seed-backed coverage sections from package assets."""
    package_root = tmp_path / "site-packages" / "dcs_simulation_engine"
    _make_packaged_report_assets(package_root)
    workdir = tmp_path / "work"
    workdir.mkdir()
    output_path = workdir / "npc_coverage.html"
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(assets, "package_root", lambda: package_root)

    result = _RUNNER.invoke(
        app,
        [
            "report",
            "results",
            str(_EXAMPLE_RESULTS),
            "--only",
            "npc-coverage",
            "--report-path",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    html = output_path.read_text(encoding="utf-8")
    assert "<html" in html
    assert 'class="alert alert-danger"' not in html
    assert "No non-human characters found." in html
