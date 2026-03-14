"""Unit tests for SessionManager persistence behavior and provider query return types."""

from typing import Any

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    PlayerRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


@pytest.fixture
def consenting_player_id(async_mongo_provider: Any) -> str:
    """Insert a consenting player row and return its id as a string."""
    db = async_mongo_provider.get_db()
    player_id = ObjectId()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": player_id,
            "consent_signature": {"answer": ["I confirm participation."]},
            "full_name": "Session Test User",
            "email": "session-test@example.com",
        }
    )
    return str(player_id)


async def _play_and_persist_session(*, provider: Any, game_name: str, player_id: str) -> SessionManager:
    """Play minimal turns for a game and persist the run by exiting."""
    session = await SessionManager.create_async(
        game=game_name,
        provider=provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=player_id,
    )
    enter_events = await session.step_async("")
    turn_events = await session.step_async("I look around")
    assert enter_events
    assert turn_events
    await session.exit_async("test complete")
    return session


class _InsertOneResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class _FakeAsyncCollection:
    """Minimal async collection wrapper for transcript-persistence tests."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def insert_many(self, docs: list[dict[str, Any]], ordered: bool = True) -> None:
        _ = ordered
        self.docs.extend(dict(doc) for doc in docs)

    async def insert_one(self, doc: dict[str, Any]) -> _InsertOneResult:
        self.docs.append(dict(doc))
        return _InsertOneResult(str(len(self.docs)))

    async def update_one(self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> None:
        match_idx = None
        for idx, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in filt.items()):
                match_idx = idx
                break
        if match_idx is None:
            if not upsert:
                return
            base = dict(filt)
            base.update(update.get("$setOnInsert", {}))
            base.update(update.get("$set", {}))
            self.docs.append(base)
            return
        self.docs[match_idx].update(update.get("$set", {}))


class _FakeAsyncDB(dict):
    """Mapping-like async DB shim keyed by collection name."""

    def __getitem__(self, key: str) -> _FakeAsyncCollection:  # type: ignore[override]
        return dict.__getitem__(self, key)


class _FakePersistenceProvider:
    """Provider stub that only exposes get_db() for async transcript persistence."""

    def __init__(self, db: _FakeAsyncDB) -> None:
        self._db = db

    def get_db(self) -> _FakeAsyncDB:
        return self._db


async def _run_session_with_async_persistence(
    *,
    provider: Any,
    persistence_db: _FakeAsyncDB,
    player_id: str,
    session_id: str,
    inputs: list[str],
) -> list[dict[str, Any]]:
    """Run a persisted session lifecycle on a single event loop."""
    session = await SessionManager.create_async(
        game="Explore",
        provider=provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=player_id,
    )
    session._provider = _FakePersistenceProvider(persistence_db)
    await session.start_persistence(session_id=session_id)

    for user_input in inputs:
        await session.step_async(user_input)
    await session.exit_async("test complete")
    return persistence_db[MongoColumns.SESSION_EVENTS].docs


async def test_query_methods_return_expected_types_after_gameplay(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
) -> None:
    """Provider query methods return expected data and runtime types."""
    _ = patch_llm_client
    await _play_and_persist_session(provider=async_mongo_provider, game_name="Explore", player_id=consenting_player_id)
    db = async_mongo_provider.get_db()
    assert "runs" not in db.list_collection_names()

    player = await async_mongo_provider.get_player(player_id=consenting_player_id)
    assert isinstance(player, PlayerRecord)

    keyed_player, raw_key = await async_mongo_provider.create_player(
        player_data={"name": "Type Check User"},
        issue_access_key=True,
    )
    assert raw_key is not None
    key_lookup = await async_mongo_provider.get_players(access_key=raw_key)
    assert isinstance(key_lookup, PlayerRecord)
    assert key_lookup.id == keyed_player.id

    characters = await async_mongo_provider.get_characters()
    assert isinstance(characters, list)
    assert characters
    assert all(isinstance(character, CharacterRecord) for character in characters)

    one_character = await async_mongo_provider.get_character(hid=characters[0].hid)
    assert isinstance(one_character, CharacterRecord)


async def test_session_events_persist_normal_turn_with_user_and_npc_messages(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
) -> None:
    """A normal gameplay turn persists user input plus NPC message rows."""
    _ = patch_llm_client
    persistence_db = _FakeAsyncDB(
        {
            MongoColumns.SESSIONS: _FakeAsyncCollection(),
            MongoColumns.SESSION_EVENTS: _FakeAsyncCollection(),
        }
    )
    rows = await _run_session_with_async_persistence(
        provider=async_mongo_provider,
        persistence_db=persistence_db,
        player_id=consenting_player_id,
        session_id="session-normal-turn",
        inputs=["", "I look around"],
    )
    assert any(
        row["direction"] == "internal" and row["event_source"] == "system" and row["event_type"] == "session_start"
        for row in rows
    )
    assert any(
        row["direction"] == "inbound"
        and row["event_source"] == "user"
        and row["event_type"] == "message"
        and row["content"] == "I look around"
        for row in rows
    )
    assert any(
        row["direction"] == "outbound"
        and row["event_source"] == "npc"
        and row["event_type"] == "message"
        and row["content"] == "The flatworm moves slowly across the surface."
        for row in rows
    )
    assert any(
        row["direction"] == "internal" and row["event_source"] == "system" and row["event_type"] == "session_end"
        for row in rows
    )


async def test_session_events_persist_recognized_commands_as_command_rows(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
) -> None:
    """Recognized slash commands persist as command input/output rows."""
    _ = patch_llm_client
    persistence_db = _FakeAsyncDB(
        {
            MongoColumns.SESSIONS: _FakeAsyncCollection(),
            MongoColumns.SESSION_EVENTS: _FakeAsyncCollection(),
        }
    )
    rows = await _run_session_with_async_persistence(
        provider=async_mongo_provider,
        persistence_db=persistence_db,
        player_id=consenting_player_id,
        session_id="session-command-turn",
        inputs=["", "/help"],
    )
    assert any(
        row["direction"] == "inbound"
        and row["event_source"] == "user"
        and row["event_type"] == "command"
        and row["content"] == "/help"
        for row in rows
    )
    assert any(
        row["direction"] == "outbound"
        and row["event_source"] == "system"
        and row["event_type"] == "command"
        and row["command_name"] == "help"
        for row in rows
    )


async def test_session_events_treat_unrecognized_slash_input_as_normal_message_turn(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
) -> None:
    """Unrecognized slash-prefixed input is not persisted as a command."""
    _ = patch_llm_client
    persistence_db = _FakeAsyncDB(
        {
            MongoColumns.SESSIONS: _FakeAsyncCollection(),
            MongoColumns.SESSION_EVENTS: _FakeAsyncCollection(),
        }
    )
    rows = await _run_session_with_async_persistence(
        provider=async_mongo_provider,
        persistence_db=persistence_db,
        player_id=consenting_player_id,
        session_id="session-unrecognized-slash",
        inputs=["", "/unknown gesture"],
    )
    assert any(
        row["direction"] == "inbound"
        and row["event_source"] == "user"
        and row["event_type"] == "message"
        and row["content"] == "/unknown gesture"
        for row in rows
    )
    assert not any(
        row["direction"] == "inbound" and row["event_type"] == "command" and row["content"] == "/unknown gesture"
        for row in rows
    )
    assert any(
        row["direction"] == "outbound"
        and row["event_source"] == "npc"
        and row["event_type"] == "message"
        and row["content"] == "The flatworm moves slowly across the surface."
        for row in rows
    )
