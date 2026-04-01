"""Unit tests for CLI dump command wiring."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import dump as dump_command
from typer.testing import CliRunner


@pytest.mark.unit
def test_dump_calls_db_dump_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dump command should create a DB handle and invoke the dump helper."""
    db = object()
    create_sync_db = MagicMock(return_value=db)
    dump_all = MagicMock(return_value=tmp_path / "2026_03_19_12_00_00")
    echo = MagicMock()

    monkeypatch.setattr(dump_command, "create_sync_db", create_sync_db)
    monkeypatch.setattr(dump_command, "dump_all_collections_to_json", dump_all)
    monkeypatch.setattr(dump_command, "echo", echo)

    ctx = SimpleNamespace(obj=SimpleNamespace(mongo_uri="mongodb://example"))
    outdir = tmp_path / "dump"
    dump_command.dump(ctx=ctx, outdir=outdir)  # type: ignore[arg-type]

    create_sync_db.assert_called_once_with(mongo_uri="mongodb://example")
    dump_all.assert_called_once_with(db, outdir)
    echo.assert_called_once()
    assert "Dump written to:" in echo.call_args.args[1]


@pytest.mark.unit
def test_cli_dump_command_is_wired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Root CLI app should expose the dump command."""
    create_sync_db = MagicMock(return_value=object())
    dump_all = MagicMock(return_value=tmp_path / "2026_03_19_12_00_00")

    monkeypatch.setattr(dump_command, "create_sync_db", create_sync_db)
    monkeypatch.setattr(dump_command, "dump_all_collections_to_json", dump_all)

    runner = CliRunner()
    result = runner.invoke(app, ["dump", str(tmp_path)])

    assert result.exit_code == 0
    assert "Dump written to:" in result.stdout
