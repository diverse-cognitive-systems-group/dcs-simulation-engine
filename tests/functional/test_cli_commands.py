"""Functional tests for CLI commands.

All tests in this file are xfailed pending CLI refactor from dcs-utils.
"""

import pytest

pytestmark = [pytest.mark.functional, pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")]

# ---------------------------------------------------------------------------
# ENGINE LIFECYCLE
# ---------------------------------------------------------------------------


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_run():
#     """Dcs run should start the engine locally without error."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_run_remote():
#     """Dcs run --remote should deploy and start the engine on Fly.io."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_status():
#     """Dcs status should report the status of active remote runs."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_stop():
#     """Dcs stop should stop the running engine."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_stop_destroy():
#     """Dcs stop --destroy should stop the engine and tear down Fly apps."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_save():
#     """Dcs save [outdir] should dump db and logs at any point during a run."""
#     ...


# # ---------------------------------------------------------------------------
# # REPORTS
# # ---------------------------------------------------------------------------


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_report_coverage():
#     """Dcs report coverage should generate a scenario coverage report."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_report_results():
#     """Dcs report results should generate a results report."""
#     ...


# # ---------------------------------------------------------------------------
# # ADMIN
# # ---------------------------------------------------------------------------


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_server_start():
#     """Dcs admin server start [opts] should start the API server."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_db_seed():
#     """Dcs admin db seed <dir> should seed the database from a directory."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_db_backup():
#     """Dcs admin db backup [outdir] should back up the database."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_db_keygen():
#     """Dcs admin db keygen should generate a deployment admin key."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_publish_character():
#     """Dcs admin publish characters --report-path <path> should publish characters."""
#     ...


# # ---------------------------------------------------------------------------
# # HITL / SIMULATION QA
# # ---------------------------------------------------------------------------


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_hitl_create():
#     """Dcs admin hitl create [opts] should scaffold HITL test scenarios."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_hitl_update():
#     """Dcs admin hitl update [opts] should update existing HITL scenarios."""
#     ...


# @pytest.mark.xfail(reason="pending CLI refactor — not yet implemented")
# def test_dcs_admin_hitl_export():
#     """Dcs admin hitl export [opts] should export scenarios to analysis-compatible run results."""
#     ...
