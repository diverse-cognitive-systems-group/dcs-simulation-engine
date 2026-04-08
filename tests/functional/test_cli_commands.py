"""Functional tests for CLI commands.

All tests in this file are skipped pending CLI refactor from dcs-utils.

These stubs document the expected CLI surface area for the `dcs` command.
Contributors implementing the CLI refactor should activate each test as
the corresponding command is implemented.

Expected commands after refactor:

    # ENGINE LIFECYCLE — all users
    dcs run [--remote]        # run locally; --remote deploys+starts on Fly
    dcs status                # check status of remote runs (Fly)
    dcs stop [--destroy]      # stop engine; --destroy tears down Fly apps
    dcs save [outdir]         # dump db + logs at any point during a run

    # REPORTS — all users
    dcs report coverage
    dcs report results

    # ADMIN — power users only
    dcs admin server start [opts]
    dcs admin db seed <dir>
    dcs admin db backup [outdir]
    dcs admin db keygen
    dcs admin publish characters --report-path <path>

    # HITL / SIMULATION QA — power users only
    dcs admin hitl create [opts]
    dcs admin hitl update [opts]
    dcs admin hitl export [opts]
"""

import pytest

pytestmark = pytest.mark.functional

# ---------------------------------------------------------------------------
# ENGINE LIFECYCLE
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending CLI refactor — dcs run not yet implemented")
def test_dcs_run():
    """Dcs run should start the engine locally without error."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs run --remote not yet implemented")
def test_dcs_run_remote():
    """Dcs run --remote should deploy and start the engine on Fly.io."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs status not yet implemented")
def test_dcs_status():
    """Dcs status should report the status of active remote runs."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs stop not yet implemented")
def test_dcs_stop():
    """Dcs stop should stop the running engine."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs stop --destroy not yet implemented")
def test_dcs_stop_destroy():
    """Dcs stop --destroy should stop the engine and tear down Fly apps."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs save not yet implemented")
def test_dcs_save():
    """Dcs save [outdir] should dump db and logs at any point during a run."""
    ...


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending CLI refactor — dcs report coverage not yet implemented")
def test_dcs_report_coverage():
    """Dcs report coverage should generate a scenario coverage report."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs report results not yet implemented")
def test_dcs_report_results():
    """Dcs report results should generate a results report."""
    ...


# ---------------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending CLI refactor — dcs admin server start not yet implemented")
def test_dcs_admin_server_start():
    """Dcs admin server start [opts] should start the API server."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin db seed not yet implemented")
def test_dcs_admin_db_seed():
    """Dcs admin db seed <dir> should seed the database from a directory."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin db backup not yet implemented")
def test_dcs_admin_db_backup():
    """Dcs admin db backup [outdir] should back up the database."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin db keygen not yet implemented")
def test_dcs_admin_db_keygen():
    """Dcs admin db keygen should generate a deployment admin key."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin publish characters not yet implemented")
def test_dcs_admin_publish_character():
    """Dcs admin publish characters --report-path <path> should publish characters."""
    ...


# ---------------------------------------------------------------------------
# HITL / SIMULATION QA
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="pending CLI refactor — dcs admin hitl create not yet implemented")
def test_dcs_admin_hitl_create():
    """Dcs admin hitl create [opts] should scaffold HITL test scenarios."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin hitl update not yet implemented")
def test_dcs_admin_hitl_update():
    """Dcs admin hitl update [opts] should update existing HITL scenarios."""
    ...


@pytest.mark.skip(reason="pending CLI refactor — dcs admin hitl export not yet implemented")
def test_dcs_admin_hitl_export():
    """Dcs admin hitl export [opts] should export scenarios to analysis-compatible run results."""
    ...
