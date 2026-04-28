"""Unit tests for CLI server command wiring."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.commands import server as server_command


@pytest.mark.unit
def test_server_wires_fake_ai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server command should pass fake_ai_response into ai_client override setter."""
    app = object()
    create_app = MagicMock(return_value=app)
    set_fake = MagicMock()
    validate_config = MagicMock()
    run_server = MagicMock()

    monkeypatch.setattr(server_command, "create_app", create_app)
    monkeypatch.setattr(server_command.ai_client, "set_fake_ai_response", set_fake)
    monkeypatch.setattr(server_command.ai_client, "validate_openrouter_configuration", validate_config)
    monkeypatch.setattr("uvicorn.run", run_server)

    ctx = SimpleNamespace(obj=None)
    server_command.server(
        ctx=ctx,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=9000,
        ttl_seconds=3600,
        sweep_interval_seconds=60,
        mongo_seed_dir=None,
        dump_dir=None,
        fake_ai_response='{"type":"ai","content":"test"}',
        config=Path("examples/run_configs/demo.yml"),
    )

    set_fake.assert_called_once_with('{"type":"ai","content":"test"}')
    validate_config.assert_called_once_with()
    assert create_app.call_args.kwargs["server_mode"] == "standard"
    assert create_app.call_args.kwargs["shutdown_dump_dir"] is None
    run_server.assert_called_once_with(app, host="127.0.0.1", port=9000, loop="uvloop", workers=1)


@pytest.mark.unit
def test_server_wires_run_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server command should pass the selected run config path through to the app factory."""
    app = object()
    create_app = MagicMock(return_value=app)

    monkeypatch.setattr(server_command, "create_app", create_app)
    monkeypatch.setattr(server_command.ai_client, "set_fake_ai_response", MagicMock())
    monkeypatch.setattr(server_command.ai_client, "validate_openrouter_configuration", MagicMock())
    monkeypatch.setattr("uvicorn.run", MagicMock())

    ctx = SimpleNamespace(obj=None)
    server_command.server(
        ctx=ctx,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=9000,
        ttl_seconds=3600,
        sweep_interval_seconds=60,
        mongo_seed_dir=None,
        dump_dir=None,
        fake_ai_response=None,
        config=Path("examples/run_configs/usability.yml"),
    )

    assert create_app.call_args.kwargs["server_mode"] == "standard"
    assert create_app.call_args.kwargs["run_config_path"] == Path("examples/run_configs/usability.yml")


@pytest.mark.unit
def test_server_wires_shutdown_dump_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Server command should pass the shutdown dump directory through to the app factory."""
    app = object()
    create_app = MagicMock(return_value=app)

    monkeypatch.setattr(server_command, "create_app", create_app)
    monkeypatch.setattr(server_command.ai_client, "set_fake_ai_response", MagicMock())
    monkeypatch.setattr(server_command.ai_client, "validate_openrouter_configuration", MagicMock())
    monkeypatch.setattr("uvicorn.run", MagicMock())

    ctx = SimpleNamespace(obj=None)
    server_command.server(
        ctx=ctx,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=9000,
        ttl_seconds=3600,
        sweep_interval_seconds=60,
        mongo_seed_dir=None,
        dump_dir=tmp_path,
        fake_ai_response=None,
        config=Path("examples/run_configs/demo.yml"),
    )

    assert create_app.call_args.kwargs["shutdown_dump_dir"] == tmp_path


@pytest.mark.unit
def test_server_wires_remote_management_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server command should pass remote-management settings through to the app factory."""
    app = object()
    create_app = MagicMock(return_value=app)

    monkeypatch.setattr(server_command, "create_app", create_app)
    monkeypatch.setattr(server_command.ai_client, "set_fake_ai_response", MagicMock())
    monkeypatch.setattr(server_command.ai_client, "validate_openrouter_configuration", MagicMock())
    monkeypatch.setattr("uvicorn.run", MagicMock())

    ctx = SimpleNamespace(obj=None)
    server_command.server(
        ctx=ctx,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=9000,
        ttl_seconds=3600,
        sweep_interval_seconds=60,
        mongo_seed_dir=None,
        dump_dir=None,
        fake_ai_response=None,
        config=Path("examples/run_configs/demo.yml"),
        remote_managed=True,
        bootstrap_token="bootstrap-secret",
        cors_origin=["https://ui.example"],
    )

    assert create_app.call_args.kwargs["remote_management_enabled"] is True
    assert create_app.call_args.kwargs["run_config_path"] == Path("examples/run_configs/demo.yml")
    assert create_app.call_args.kwargs["bootstrap_token"] == "bootstrap-secret"
    assert create_app.call_args.kwargs["cors_origins"] == ["https://ui.example"]
