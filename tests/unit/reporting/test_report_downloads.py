"""Tests for downloadable artifacts in generated reports."""

import base64
import json
import re
import zipfile
from io import BytesIO

import pytest
import yaml
from dcs_simulation_engine.reporting.auto import resolve_sections, run_analysis
from dcs_simulation_engine.reporting.loader import load_all

pytestmark = pytest.mark.unit


def test_results_report_embeds_raw_results_and_db_run_config(tmp_path) -> None:
    """Generated reports should offer raw results and the persisted run config as downloads."""
    (tmp_path / "runs.json").write_text(
        json.dumps(
            [
                {
                    "name": "download-test",
                    "description": "Download artifact test",
                    "config_snapshot": {
                        "name": "download-test",
                        "description": "Stored in the run record",
                        "games": [{"name": "Explore"}],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "assignments.json").write_text(
        json.dumps([{"status": "completed"}, {"status": "pending"}]),
        encoding="utf-8",
    )

    data = load_all(tmp_path)
    html = run_analysis(data, sections=resolve_sections(only=["metadata"], include=None, exclude=None))
    artifacts = _artifacts_from(html)

    raw_results = artifacts["raw_results"]
    assert raw_results["filename"] == f"{tmp_path.name}.zip"
    with zipfile.ZipFile(BytesIO(base64.b64decode(raw_results["b64"]))) as archive:
        assert f"{tmp_path.name}/runs.json" in archive.namelist()
        assert f"{tmp_path.name}/assignments.json" in archive.namelist()

    run_config = yaml.safe_load(base64.b64decode(artifacts["run_config"]["b64"]).decode("utf-8"))
    assert run_config["name"] == "download-test"
    assert run_config["description"] == "Stored in the run record"


def _artifacts_from(html: str) -> dict:
    match = re.search(r"var _artifacts = (.*?);", html)
    assert match is not None
    return json.loads(match.group(1))
