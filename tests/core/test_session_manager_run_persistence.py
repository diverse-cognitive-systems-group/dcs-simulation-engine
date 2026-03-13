"""Unit tests for SessionManager persistence behavior and provider query return types."""

import asyncio
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


@pytest.fixture
def consenting_player_id(mongo_provider: Any) -> str:
    """Insert a consenting player row and return its id as a string."""
    db = mongo_provider.get_db()
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


def _play_and_persist_session(*, provider: Any, game_name: str, player_id: str) -> SessionManager:
    """Play minimal turns for a game and persist the run by exiting."""
    session = asyncio.run(
        SessionManager.create_async(
            game=game_name,
            provider=provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=player_id,
        )
    )
    enter_events = list(session.step(""))
    turn_events = list(session.step("I look around"))
    assert enter_events
    assert turn_events
    session.exit(reason="test complete")
    return session


@pytest.mark.unit
def test_query_methods_return_expected_types_after_gameplay(
    patch_llm_client: Any,
    mongo_provider: Any,
    consenting_player_id: str,
) -> None:
    """Provider query methods return expected data and runtime types."""
    _ = patch_llm_client
    _play_and_persist_session(provider=mongo_provider, game_name="Explore", player_id=consenting_player_id)
    db = mongo_provider.get_db()
    assert "runs" not in db.list_collection_names()

    player = mongo_provider.get_player(player_id=consenting_player_id)
    assert isinstance(player, PlayerRecord)

    keyed_player, raw_key = mongo_provider.create_player(player_data={"name": "Type Check User"}, issue_access_key=True)
    assert raw_key is not None
    key_lookup = mongo_provider.get_players(access_key=raw_key)
    assert isinstance(key_lookup, PlayerRecord)
    assert key_lookup.id == keyed_player.id

    characters = mongo_provider.get_characters()
    assert isinstance(characters, list)
    assert characters
    assert all(isinstance(character, CharacterRecord) for character in characters)

    one_character = mongo_provider.get_character(hid=characters[0].hid)
    assert isinstance(one_character, CharacterRecord)
