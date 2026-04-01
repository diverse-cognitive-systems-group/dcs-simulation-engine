"""Unit tests for the FastAPI session registry."""

from datetime import datetime, timedelta, timezone

import pytest
from dcs_simulation_engine.api.registry import SessionRegistry

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


class DummyManager:
    """Minimal session-manager stub for registry tests."""

    def __init__(self) -> None:
        """Initialize minimal exit state fields used by tests."""
        self._exited = False
        self.exit_reason = ""

    @property
    def exited(self) -> bool:
        """Whether the manager has exited."""
        return self._exited

    async def exit_async(self, reason: str) -> None:
        """Mark manager as exited with a reason."""
        self._exited = True
        self.exit_reason = reason


async def test_registry_add_get_list_touch_remove() -> None:
    """Registry supports core CRUD and touch operations."""
    registry = SessionRegistry(ttl_seconds=3600, sweep_interval_seconds=600)

    manager_a = DummyManager()
    manager_b = DummyManager()

    entry_a = registry.add(player_id="player-a", game_name="explore", manager=manager_a)  # type: ignore[arg-type]
    entry_b = registry.add(player_id="player-b", game_name="foresight", manager=manager_b)  # type: ignore[arg-type]

    assert registry.get(entry_a.session_id) is not None
    assert registry.get(entry_b.session_id) is not None

    player_a_sessions = registry.list_for_player("player-a")
    assert len(player_a_sessions) == 1
    assert player_a_sessions[0].session_id == entry_a.session_id

    old_last_active = entry_a.last_active
    registry.touch(entry_a.session_id)
    assert registry.get(entry_a.session_id).last_active >= old_last_active  # type: ignore[union-attr]

    removed = registry.remove(entry_a.session_id)
    assert removed is not None
    assert registry.get(entry_a.session_id) is None


async def test_registry_sweep_expires_idle_sessions() -> None:
    """Sweep removes stale sessions and exits their managers."""
    registry = SessionRegistry(ttl_seconds=1, sweep_interval_seconds=600)
    manager = DummyManager()

    entry = registry.add(player_id="player-a", game_name="explore", manager=manager)  # type: ignore[arg-type]
    entry.last_active = datetime.now(timezone.utc) - timedelta(seconds=10)

    removed_ids = await registry.sweep_async()

    assert entry.session_id in removed_ids
    assert registry.get(entry.session_id) is None
    assert manager.exited is True
    assert manager.exit_reason == "session ttl expired"
