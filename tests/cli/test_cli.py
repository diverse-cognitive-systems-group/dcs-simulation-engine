"""Tests for the CLI module."""

import pytest


@pytest.mark.unit
def test_can_import_cli() -> None:
    """Ensure the main CLI module can be imported."""
    import dcs_simulation_engine.cli.app as a

    assert a.app


@pytest.mark.skip(reason="CLI startup test not implemented yet")
def test_can_start_cli() -> None:
    """Ensure the CLI can be started."""
    pass
