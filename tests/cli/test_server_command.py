"""Unit tests for CLI server command wiring."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.commands import server as server_command


@pytest.mark.unit
def test_server_wires_fake_ai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Server command should pass fake_ai_response into ai_client override setter."""
    app = object()
    set_fake = MagicMock()
    validate_config = MagicMock()
    run_server = MagicMock()

    monkeypatch.setattr(server_command, "create_app", lambda **_kwargs: app)
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
        fake_ai_response='{"type":"ai","content":"test"}',
    )

    set_fake.assert_called_once_with('{"type":"ai","content":"test"}')
    validate_config.assert_called_once_with()
    run_server.assert_called_once_with(app, host="127.0.0.1", port=9000, loop="uvloop", workers=1)
