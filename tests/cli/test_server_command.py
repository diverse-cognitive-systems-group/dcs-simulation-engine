"""Unit tests for CLI server command wiring."""

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
        free_play=False,
    )

    set_fake.assert_called_once_with('{"type":"ai","content":"test"}')
    validate_config.assert_called_once_with()
    assert create_app.call_args.kwargs["server_mode"] == "standard"
    assert create_app.call_args.kwargs["shutdown_dump_dir"] is None
    run_server.assert_called_once_with(app, host="127.0.0.1", port=9000, loop="uvloop", workers=1)


@pytest.mark.unit
def test_server_wires_free_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server command should pass free-play mode through to the app factory."""
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
        free_play=True,
    )

    assert create_app.call_args.kwargs["server_mode"] == "free_play"


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
        free_play=False,
    )

    assert create_app.call_args.kwargs["shutdown_dump_dir"] == tmp_path
