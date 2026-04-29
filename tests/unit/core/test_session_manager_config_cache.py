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
    previous_run_config = SessionManager._run_config
    SessionManager._run_config = None
    SessionManager._game_config_cache.clear()
    load_calls = {"count": 0}

    class _FakeGame:
        GAME_NAME = "Explore"

    def _fake_from_game_class(_game_cls, *, overrides=None) -> _DummyConfig:
        assert _game_cls is _FakeGame
        assert overrides == {}
        load_calls["count"] += 1
        return _DummyConfig()

    monkeypatch.setattr(SessionManager, "_builtin_game_classes", classmethod(lambda cls: {"explore": _FakeGame}))
    monkeypatch.setattr("dcs_simulation_engine.core.session_manager.GameConfig.from_game_class", _fake_from_game_class)

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
        SessionManager._run_config = previous_run_config
