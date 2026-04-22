"""Functional coverage for persisted session events and scorer prompt contracts."""

import inspect
import json
from typing import Any
from uuid import uuid4

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.ai_client import ScorerResult
from pymongo.database import Database

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()

EVALUATION_GAME_CASES = [
    {
        "game": "Infer Intent",
        "turn_input": "I observe the creature carefully.",
        "finish_inputs": [
            "The creature is trying to find safety.",
            "Very confident because it repeatedly avoids bright areas.",
        ],
        "prompt_expectations": [
            "Interaction Transcript",
            "Player's Goal Inference Prediction",
            "The creature is trying to find safety.",
            "I observe the creature carefully.",
        ],
    },
    {
        "game": "Goal Horizon",
        "turn_input": "I place an object nearby and observe.",
        "finish_inputs": [
            "It seems limited to local sensing and cautious movement.",
            "Fairly confident based on repeated avoidance behavior.",
        ],
        "prompt_expectations": [
            "Interaction Transcript",
            "Player Guess",
            "It seems limited to local sensing and cautious movement.",
        ],
    },
    {
        "game": "foresight",
        "turn_input": "I wave my hand and predict they will wave back.",
        "finish_inputs": [],
        "prompt_expectations": [
            "Interaction Transcript",
            "I wave my hand and predict they will wave back.",
            "Predictions were mostly absent, implausible, or out of character.",
        ],
    },
    {
        "game": "teamwork",
        "turn_input": "I move toward the loose panel.",
        "finish_inputs": [
            "Coordinating timing with FW was the hardest part.",
        ],
        "prompt_expectations": [
            "Shared Goal",
            "to secure the exposed control box before the room fully floods",
            "I move toward the loose panel.",
        ],
    },
]


def _make_collection_async(coll: Any) -> None:
    """Wrap mongomock write methods with async callables for persistence tests."""
    for method_name in ("insert_one", "insert_many", "update_one"):
        method = getattr(coll, method_name, None)
        if method is None or inspect.iscoroutinefunction(method):
            continue

        async def _async_method(*args: Any, __method: Any = method, **kwargs: Any) -> Any:
            return __method(*args, **kwargs)

        setattr(coll, method_name, _async_method)


def _enable_async_mongo_writes(db: Database[Any]) -> None:
    """Enable async-compatible writes for session persistence collections."""
    _make_collection_async(db[MongoColumns.SESSIONS])
    _make_collection_async(db[MongoColumns.SESSION_EVENTS])


def _persisted_events(db: Database[Any], *, session_id: str) -> list[dict[str, Any]]:
    """Return ordered persisted events for one session."""
    return list(db[MongoColumns.SESSION_EVENTS].find({MongoColumns.SESSION_ID: session_id}).sort(MongoColumns.SEQ, 1))


def _matching_events(
    events: list[dict[str, Any]],
    *,
    direction: str,
    event_source: str,
    event_type: str,
) -> list[dict[str, Any]]:
    """Return persisted events matching one normalized classification."""
    return [
        event
        for event in events
        if event.get(MongoColumns.DIRECTION) == direction
        and event.get(MongoColumns.EVENT_SOURCE) == event_source
        and event.get(MongoColumns.EVENT_TYPE) == event_type
    ]


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state: Database[Any], async_mongo_provider: Any) -> None:
    """Seed a consenting player record for gated game flows."""
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": TEST_PLAYER_ID,
            "consent_signature": {"answer": ["I confirm that the information I have provided is true..."]},
            "full_name": "Persistence Flow Test Player",
            "email": "persistence-flow@example.com",
        }
    )


async def _make_persisted_session(*, game: str, async_mongo_provider: Any) -> tuple[SessionManager, str, Database[Any]]:
    """Create a real session with event persistence enabled."""
    db = async_mongo_provider.get_db()
    _enable_async_mongo_writes(db)
    player_id = str(TEST_PLAYER_ID) if game.lower() != "explore" else None
    session = await SessionManager.create_async(
        game=game,
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=player_id,
    )
    session_id = f"persisted-session-{uuid4().hex}"
    await session.start_persistence(session_id=session_id)
    return session, session_id, db


async def _complete_evaluation_game(
    session: SessionManager, *, game: str, turn_input: str, finish_inputs: list[str]
) -> list[dict[str, Any]]:
    """Drive one full evaluation flow and return the completion events."""
    enter_events = await session.step_async("")
    assert enter_events
    turn_events = await session.step_async(turn_input)
    assert turn_events
    completion_events: list[dict[str, Any]] = []

    finish_events = await session.step_async("/finish")
    if game == "foresight":
        completion_events = finish_events
    else:
        assert finish_events
        for follow_up in finish_inputs:
            completion_events = await session.step_async(follow_up)

    assert completion_events
    assert session.exited
    return completion_events


@pytest.mark.parametrize("case", EVALUATION_GAME_CASES, ids=lambda case: case["game"])
async def test_evaluation_score_events_persist_as_system_info_rows(
    case: dict[str, Any],
    patch_llm_client: Any,
    async_mongo_provider: Any,
) -> None:
    """Final score content should persist as visible outbound system info."""
    _ = patch_llm_client
    session, session_id, db = await _make_persisted_session(game=case["game"], async_mongo_provider=async_mongo_provider)

    completion_events = await _complete_evaluation_game(
        session,
        game=case["game"],
        turn_input=case["turn_input"],
        finish_inputs=case["finish_inputs"],
    )

    score_content = completion_events[0]["content"]
    events = _persisted_events(db, session_id=session_id)
    score_rows = [
        event
        for event in _matching_events(events, direction="outbound", event_source="system", event_type="info")
        if event[MongoColumns.CONTENT] == score_content
    ]

    assert len(score_rows) == 1
    assert score_rows[0][MongoColumns.VISIBLE_TO_USER] is True
    assert score_rows[0][MongoColumns.TURN_INDEX] == session.turns + 1


async def test_player_validation_failures_are_persisted_with_schema(
    monkeypatch: pytest.MonkeyPatch,
    async_mongo_provider: Any,
) -> None:
    """Rejected player actions should persist a validation_violation row with structured JSON payload."""
    import dcs_simulation_engine.games.ai_client as ai_client

    async def fake_call_openrouter(messages: list[dict[str, str]], model: str) -> str:
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            system_prompt = messages[0]["content"]
            if "RULE: VALID-PC-ABILITY" in system_prompt:
                return '{"pass": false, "reason": "That action exceeds the player character abilities."}'
            return '{"pass": true, "reason": "ok"}'
        return '{"type": "ai", "content": "The flatworm moves slowly across the surface."}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call_openrouter)

    session, session_id, db = await _make_persisted_session(game="Explore", async_mongo_provider=async_mongo_provider)
    await session.step_async("")

    emitted = await session.step_async("I teleport through the wall.")
    await session.exit_async("test complete")

    assert [event["type"] for event in emitted] == ["error"]
    assert emitted[0]["content"] == "That action exceeds the player character abilities."

    events = _persisted_events(db, session_id=session_id)
    violations = _matching_events(
        events,
        direction="internal",
        event_source="player_validation",
        event_type="validation_violation",
    )

    assert len(violations) == 1
    payload = json.loads(violations[0][MongoColumns.CONTENT])
    assert payload["validator_name"].startswith("VALID-PC-ABILITY")
    assert payload["stage"] == "player_validation"
    assert payload["message"] == "That action exceeds the player character abilities."
    assert payload["response"] == "I teleport through the wall."
    assert payload["raw_result"]["pass"] is False


async def test_simulator_validation_failures_are_persisted_for_both_attempts(
    monkeypatch: pytest.MonkeyPatch,
    async_mongo_provider: Any,
) -> None:
    """A simulator response that fails validation twice should persist both violations."""
    import dcs_simulation_engine.games.ai_client as ai_client

    async def fake_call_openrouter(messages: list[dict[str, str]], model: str) -> str:
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            system_prompt = messages[0]["content"]
            if "RULE: VALID-NPC-ACTION" in system_prompt:
                return '{"pass": false, "reason": "Simulator response violated the NPC action rule."}'
            return '{"pass": true, "reason": "ok"}'
        return '{"type": "ai", "content": "The flatworm teleports through the wall."}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call_openrouter)

    session, session_id, db = await _make_persisted_session(game="Explore", async_mongo_provider=async_mongo_provider)
    await session.step_async("")

    emitted = await session.step_async("I wait.")
    await session.exit_async("test complete")

    assert [event["type"] for event in emitted] == ["error"]
    assert emitted[0]["content"] == "I couldn't produce a valid simulator response. Please retry your action."

    events = _persisted_events(db, session_id=session_id)
    violations = _matching_events(
        events,
        direction="internal",
        event_source="simulator_validation",
        event_type="validation_violation",
    )

    assert len(violations) == 2
    for row in violations:
        payload = json.loads(row[MongoColumns.CONTENT])
        assert payload["validator_name"].startswith("VALID-NPC-ACTION")
        assert payload["stage"] == "simulator_validation"
        assert payload["message"] == "Simulator response violated the NPC action rule."
        assert payload["response"] == "The flatworm teleports through the wall."
        assert payload["raw_result"]["pass"] is False


@pytest.mark.parametrize("case", EVALUATION_GAME_CASES, ids=lambda case: case["game"])
async def test_evaluation_games_pass_expected_fields_to_scorer_boundary(
    case: dict[str, Any],
    patch_llm_client: Any,
    async_mongo_provider: Any,
) -> None:
    """Each evaluated game should pass transcript plus its game-specific fields to the scorer."""
    _ = patch_llm_client
    session = await SessionManager.create_async(
        game=case["game"],
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    captured: dict[str, str] = {}

    async def capture_score(*, prompt: str, transcript: str) -> ScorerResult:
        captured["prompt"] = prompt
        captured["transcript"] = transcript
        return ScorerResult(evaluation={"tier": 2, "score": 65, "reasoning": "Partial match."}, raw_json="{}")

    session.game._scorer.score = capture_score  # type: ignore[method-assign]

    await _complete_evaluation_game(
        session,
        game=case["game"],
        turn_input=case["turn_input"],
        finish_inputs=case["finish_inputs"],
    )

    assert "Opening scene:" in captured["transcript"]
    assert case["turn_input"] in captured["transcript"]
    for expected in case["prompt_expectations"]:
        assert expected in captured["prompt"]
