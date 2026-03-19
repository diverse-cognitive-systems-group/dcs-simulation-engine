"""SessionManager game-config cache behavior tests."""

from copy import deepcopy

import pytest
from dcs_simulation_engine.core.session_manager import SessionManager


class _DummyConfig:
    """Small stand-in config object implementing model_copy()."""

    def __init__(self) -> None:
        self.marker: list[str] = []

    def model_copy(self, *, deep: bool = False) -> "_DummyConfig":
        if deep:
            return deepcopy(self)
        return self


@pytest.mark.unit
def test_get_game_config_cached_loads_once_and_returns_defensive_copies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config loader should run once per exact game key and callers should receive copies."""
    previous_cache = dict(SessionManager._game_config_cache)
    SessionManager._game_config_cache.clear()
    load_calls = {"count": 0}

    def _fake_get_game_config(_game: str) -> str:
        return "/tmp/explore.yaml"

    def _fake_load(_path: str) -> _DummyConfig:
        load_calls["count"] += 1
        return _DummyConfig()

    monkeypatch.setattr("dcs_simulation_engine.core.session_manager.get_game_config", _fake_get_game_config)
    monkeypatch.setattr("dcs_simulation_engine.core.session_manager.GameConfig.load", _fake_load)

    try:
        cfg1 = SessionManager.get_game_config_cached("Explore")
        cfg2 = SessionManager.get_game_config_cached("Explore")

        cfg1.marker.append("changed")

        assert load_calls["count"] == 1
        assert cfg1 is not cfg2
        assert cfg2.marker == []
    finally:
        SessionManager._game_config_cache.clear()
        SessionManager._game_config_cache.update(previous_cache)
