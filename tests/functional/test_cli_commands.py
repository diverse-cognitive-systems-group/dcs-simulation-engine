"""Workflow-level CLI coverage obligations.

This file intentionally tracks end-to-end CLI workflows rather than individual
command wiring. Keep unit-level command checks in ``tests/unit/cli`` and use
these tests for behavior that spans multiple commands, filesystem artifacts,
database state, or service lifecycle.

Each xfail below should be replaced by a real functional test when the workflow
is ready to support deterministic local testing. Use strict xfails so an
accidental pass forces the placeholder to be resolved instead of quietly aging.
"""

import pytest

pytestmark = pytest.mark.functional


def _workflow_not_covered(workflow: str) -> None:
    pytest.fail(f"Functional CLI workflow coverage is still missing for: {workflow}")


@pytest.mark.xfail(strict=True, reason="dcs run orchestration is not implemented yet")
def test_cli_local_engine_run_cycle() -> None:
    """Run a local engine stack, exercise the API/UI entrypoints, and shut it down."""
    _workflow_not_covered("local engine run cycle")


@pytest.mark.xfail(strict=True, reason="database workflow coverage should exercise real seed/backup/dump IO together")
def test_cli_database_seed_backup_dump_cycle() -> None:
    """Seed a test database, write backup/dump artifacts, and validate outputs."""
    _workflow_not_covered("database seed/backup/dump cycle")


@pytest.mark.xfail(strict=True, reason="reporting has command coverage, but not a single CLI workflow cycle")
def test_cli_reporting_cycle() -> None:
    """Generate CLI report artifacts from fixture results and validate expected files."""
    _workflow_not_covered("reporting cycle")


@pytest.mark.xfail(strict=True, reason="HITL has command coverage, but not a single full evaluation workflow")
def test_cli_hitl_evaluation_cycle() -> None:
    """Create, update, export, and report on a HITL evaluation using test doubles."""
    _workflow_not_covered("HITL evaluation cycle")


@pytest.mark.xfail(strict=True, reason="remote lifecycle needs a deterministic mocked Fly workflow")
def test_cli_remote_lifecycle_cycle() -> None:
    """Deploy, inspect, save, and stop a remote run through the CLI lifecycle."""
    _workflow_not_covered("remote lifecycle cycle")
