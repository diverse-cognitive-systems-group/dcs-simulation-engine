"""Unit tests for CLI database commands."""

from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import database as database_command
from typer.testing import CliRunner


@pytest.mark.unit
def test_database_keygen_prints_key_and_usage_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Database keygen should print a new key plus deployment-oriented guidance."""
    generated_key = "dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU"
    monkeypatch.setattr(database_command, "generate_access_key", MagicMock(return_value=generated_key))

    runner = CliRunner()
    result = runner.invoke(app, ["database", "keygen"])

    assert result.exit_code == 0
    assert generated_key in result.stdout
    assert "has not been added to any app or database" in result.stdout
    assert "intended to be supplied during deployment" in result.stdout
