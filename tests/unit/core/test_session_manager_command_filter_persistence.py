"""Unit tests for command filter triggering and Mongo event persistence."""

import inspect
from typing import Any
from uuid import uuid4

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.explore import Command as ExploreCommand
from dcs_simulation_engine.games.foresight import Command as ForesightCommand
from dcs_simulation_engine.games.goal_horizon import Command as GoalHorizonCommand
from dcs_simulation_engine.games.infer_intent import Command as InferIntentCommand
from pymongo.database import Database

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def _make_collection_async(coll: Any) -> None:
    """Wrap mongomock write methods with async callables."""
    for method_name in ("insert_one", "insert_many", "update_one"):
        method = getattr(coll, method_name, None)
        if method is None or inspect.iscoroutinefunction(method):
            continue

        async def _async_method(*args: Any, __method: Any = method, **kwargs: Any) -> Any:
            return __method(*args, **kwargs)

        setattr(coll, method_name, _async_method)


def _enable_async_mongo_writes(db: Database[Any]) -> None:
    """Enable async-compatible writes for transcript collections."""
    _make_collection_async(db[MongoColumns.SESSIONS])
    _make_collection_async(db[MongoColumns.SESSION_EVENTS])


def _expected_command_args(command_text: str) -> str:
    """Return parsed command args using recorder-equivalent parsing."""
    stripped = command_text.strip().removeprefix("/")
    parts = stripped.split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def _events_for_turn(db: Database[Any], *, session_id: str, turn_index: int) -> list[dict[str, Any]]:
    """Fetch ordered session event docs for one turn."""
    return list(
        db[MongoColumns.SESSION_EVENTS]
        .find(
            {
                MongoColumns.SESSION_ID: session_id,
                MongoColumns.TURN_INDEX: turn_index,
            }
        )
        .sort(MongoColumns.SEQ, 1)
    )


def _event_by_classification(
    events: list[dict[str, Any]],
    *,
    direction: str,
    event_type: str,
    event_source: str,
) -> dict[str, Any]:
    """Return exactly one event by persisted classification."""
    matches = [
        event
        for event in events
        if event.get(MongoColumns.DIRECTION) == direction
        and event.get(MongoColumns.EVENT_TYPE) == event_type
        and event.get(MongoColumns.EVENT_SOURCE) == event_source
    ]
    assert len(matches) == 1, f"Expected 1 event for {direction}/{event_source}/{event_type}, found {len(matches)}."
    return matches[0]


async def _create_persisted_session(
    *,
    provider: Any,
    game_name: str,
    player_id: str,
) -> tuple[SessionManager, str]:
    """Create a session, start persistence, and emit opening events."""
    session = await SessionManager.create_async(
        game=game_name,
        provider=provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=player_id,
    )
    session_id = f"test-session-{uuid4().hex}"
    await session.start_persistence(session_id=session_id)
    opening_events = await session.step_async(None)
    assert opening_events
    return session, session_id


@pytest.fixture
def consenting_player_id(async_mongo_provider: Any) -> str:
    """Insert a consenting player row and return its id."""
    player_id = ObjectId()
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": player_id,
            "consent_signature": {"answer": ["I confirm participation."]},
            "full_name": "Command Filter Test User",
            "email": "command-filter@example.com",
        }
    )
    return str(player_id)


@pytest.mark.parametrize(
    ("game_name", "command_text", "expected_command_name"),
    [
        ("Explore", f"/{ExploreCommand.HELP.value}", ExploreCommand.HELP.value),
        ("Explore", f"/{ExploreCommand.ABILITIES.value}", ExploreCommand.ABILITIES.value),
        ("Foresight", f"/{ForesightCommand.HELP.value}", ForesightCommand.HELP.value),
        ("Foresight", f"/{ForesightCommand.FINISH.value}", ForesightCommand.FINISH.value),
        ("Infer Intent", f"/{InferIntentCommand.HELP.value}", InferIntentCommand.HELP.value),
        ("Infer Intent", f"/{InferIntentCommand.PREDICT_INTENT.value}", InferIntentCommand.PREDICT_INTENT.value),
        ("Goal Horizon", f"/{GoalHorizonCommand.HELP.value}", GoalHorizonCommand.HELP.value),
        ("Goal Horizon", f"/{GoalHorizonCommand.PREDICT_CAPABILITIES.value}", GoalHorizonCommand.PREDICT_CAPABILITIES.value),
    ],
)
async def test_game_level_command_filters_persist_command_events(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
    game_name: str,
    command_text: str,
    expected_command_name: str,
) -> None:
    """Game-level slash commands should persist as command input/output events."""
    _ = patch_llm_client
    db = async_mongo_provider.get_db()
    _enable_async_mongo_writes(db)

    session, session_id = await _create_persisted_session(
        provider=async_mongo_provider,
        game_name=game_name,
        player_id=consenting_player_id,
    )

    turn_index = session.turns + 1
    emitted = await session.step_async(command_text)
    assert emitted
    assert emitted[0]["type"] == "info"

    if not session.exited:
        await session.exit_async("test complete")

    turn_events = _events_for_turn(db, session_id=session_id, turn_index=turn_index)
    command_input = _event_by_classification(
        turn_events,
        direction="inbound",
        event_type="command",
        event_source="user",
    )
    command_output = _event_by_classification(
        turn_events,
        direction="outbound",
        event_type="command",
        event_source="system",
    )

    assert command_input[MongoColumns.CONTENT] == command_text
    assert command_input[MongoColumns.COMMAND_NAME] == expected_command_name
    assert command_input[MongoColumns.COMMAND_ARGS] == _expected_command_args(command_text)
    assert command_output[MongoColumns.CONTENT] == emitted[0]["content"]


@pytest.mark.parametrize(
    ("command_text", "expected_command_name", "expected_command_args", "expect_exit"),
    [
        ("/exit", "exit", "", True),
    ],
)
async def test_session_level_exit_command_persists_and_normalizes_reason(
    patch_llm_client: Any,
    async_mongo_provider: Any,
    consenting_player_id: str,
    command_text: str,
    expected_command_name: str,
    expected_command_args: str,
    expect_exit: bool,
) -> None:
    """Session-level exit command should persist command events and normalize exit reasons."""
    _ = patch_llm_client
    db = async_mongo_provider.get_db()
    _enable_async_mongo_writes(db)

    session, session_id = await _create_persisted_session(
        provider=async_mongo_provider,
        game_name="Explore",
        player_id=consenting_player_id,
    )

    turn_index = session.turns + 1
    emitted = await session.step_async(command_text)
    assert emitted
    assert emitted[0]["type"] == "info"

    if expect_exit:
        assert session.exited
    else:
        assert not session.exited
        await session.exit_async("test complete")

    turn_events = _events_for_turn(db, session_id=session_id, turn_index=turn_index)
    command_input = _event_by_classification(
        turn_events,
        direction="inbound",
        event_type="command",
        event_source="user",
    )
    command_output = _event_by_classification(
        turn_events,
        direction="outbound",
        event_type="command",
        event_source="system",
    )

    assert command_input[MongoColumns.CONTENT] == command_text
    assert command_input[MongoColumns.COMMAND_NAME] == expected_command_name
    assert command_input[MongoColumns.COMMAND_ARGS] == expected_command_args
    assert command_output[MongoColumns.CONTENT] == emitted[0]["content"]

    if expect_exit:
        session_doc = db[MongoColumns.SESSIONS].find_one({MongoColumns.SESSION_ID: session_id})
        assert session_doc is not None
        assert session_doc[MongoColumns.TERMINATION_REASON] == "user_exit_command"
