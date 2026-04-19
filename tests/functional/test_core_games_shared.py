"""Shared functional tests parametrized over all 5 games.

Validates behaviors that every game must exhibit:
- Help content includes all required sections
- Simulator takes the first turn (ENTER produces info + AI events)
- No unrendered template brackets appear in any system output
"""

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()
FINISH_COMMAND = "/finish"

# Games that require a consenting player record in the DB
_CONSENT_GATED = {"Infer Intent", "Goal Horizon", "foresight", "teamwork"}

ALL_GAMES = ["explore", "Infer Intent", "Goal Horizon", "foresight", "teamwork"]

# Sections that must appear in /help output for every game
_REQUIRED_HELP_SECTIONS = [
    "Player Character",
    "Simulator Character",
    "Player Objective",
    "How to Play",
    "How to",  # covers both "How to Finish" and "How to finish"
    "/abilities",
    "/help",
]


@pytest.fixture(autouse=True)
def _seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a consenting player record for gated games.

    Explore is ungated and ignores player_id; having the record is harmless.
    """
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": TEST_PLAYER_ID,
            "consent_signature": {"answer": ["I confirm that the information I have provided is true..."]},
            "full_name": "Test Player",
            "email": "test@example.com",
        }
    )
    yield


async def _make_session(game: str, async_mongo_provider):
    """Create a session, passing player_id only for consent-gated games."""
    player_id = str(TEST_PLAYER_ID) if game in _CONSENT_GATED else None
    return await SessionManager.create_async(
        game=game,
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=player_id,
    )


@pytest.mark.parametrize("game", ALL_GAMES)
async def test_help_command_contains_required_sections(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Help output must include all required sections for every game.

    Checks that /help info content contains:
    Player Character, Simulator Character, Player Objective,
    How to Play, How to (finish), /abilities, /help.
    """
    session = await _make_session(game, async_mongo_provider)
    await session.step_async("")  # ENTER

    help_events = await session.step_async("/help")

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert info_events, f"[{game}] /help should return at least one info event"

    content = " ".join(e["content"] for e in info_events)
    for section in _REQUIRED_HELP_SECTIONS:
        assert section in content, f"[{game}] /help missing required section: '{section}'\nFull help content:\n{content}"


@pytest.mark.parametrize("game", ALL_GAMES)
async def test_simulator_takes_first_turn(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """ENTER must yield both a welcome info event and an AI opening turn.

    The simulator should take the first turn before any player input.
    """
    session = await _make_session(game, async_mongo_provider)

    enter_events = await session.step_async("")

    info_events = [e for e in enter_events if e.get("type") == "info"]
    ai_events = [e for e in enter_events if e.get("type") == "ai"]

    assert info_events, f"[{game}] ENTER should produce a welcome info event"
    assert ai_events, f"[{game}] ENTER should produce an AI opening turn"
    assert session.turns == 1, f"[{game}] turns should be 1 after ENTER (got {session.turns})"


@pytest.mark.parametrize("game", ALL_GAMES)
async def test_no_bracket_rendering_in_system_responses(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """No known raw format placeholders should appear in system-generated content.

    Catches unrendered format strings such as '{npc_hid}' or
    '{pc_short_description}' that indicate a template rendering failure.
    Exercises: ENTER, 3 normal turns, /help, /abilities, finish command.
    """
    session = await _make_session(game, async_mongo_provider)
    all_events: list[dict] = []

    all_events.extend(await session.step_async(""))  # ENTER

    for action in ["I look around", "I move closer", "I wait"]:
        if not session.exited:
            all_events.extend(await session.step_async(action))

    if not session.exited:
        all_events.extend(await session.step_async("/help"))
    if not session.exited:
        all_events.extend(await session.step_async("/abilities"))

    # Issue the finish command to check its prompt for bracket rendering
    if not session.exited:
        all_events.extend(await session.step_async(FINISH_COMMAND))

    placeholder_tokens = (
        "{pc_hid}",
        "{pc_short_description}",
        "{pc_long_description}",
        "{pc_abilities}",
        "{pc_goals}",
        "{pc_scenarios}",
        "{npc_hid}",
        "{npc_short_description}",
        "{npc_long_description}",
        "{npc_abilities}",
        "{npc_goals}",
        "{npc_scenarios}",
        "{player_action}",
        "{simulator_response}",
        "{transcript}",
        "{game_objective}",
        "{guess}",
        "{shared_goal}",
        "{finish_reason}",
    )

    for event in all_events:
        content = event.get("content", "")
        assert not any(token in content for token in placeholder_tokens), (
            f"[{game}] Unrendered format placeholder leaked into {event.get('type')} event:\n{content}"
        )


def test_save_resume_when_leaving(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Session resumes with history replay after WebSocket disconnect.

    Uses explore (ungated) since free-play mode passes player_id=None, which
    would fail consent checks for gated games. Resume behavior is game-agnostic —
    registry.pause() / _send_replay() applies equally to all games.
    """
    from dcs_simulation_engine.api.app import create_app
    from fastapi.testclient import TestClient

    app = create_app(
        provider=async_mongo_provider,
        server_mode="free_play",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/play/game",
            json={"game": "explore", "pc_choice": "NA", "npc_choice": "FW", "source": "api"},
        )
        assert resp.status_code == 200, f"Game creation failed: {resp.text}"
        session_id = resp.json()["session_id"]

        # First connection: receive opening turn, then disconnect WITHOUT close frame.
        # Exiting the context without a close frame triggers WebSocketDisconnect on the
        # server side → registry.pause(session_id) is called.
        with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
            ws.receive_json()  # session_meta
            ws.receive_json()  # opening event (type="event")
            turn_end = ws.receive_json()  # turn_end
            turns_before = turn_end.get("turns", 1)

        # Second connection: resume path — server detects entry.status == "paused"
        # and sends replay_start → (events) → replay_end before normal play resumes.
        with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
            ws.receive_json()  # session_meta (always sent first)
            replay_start = ws.receive_json()
            replay_end = ws.receive_json()

            assert replay_start.get("type") == "replay_start", f"Expected replay_start frame on reconnect, got: {replay_start}"
            assert replay_end.get("type") == "replay_end", f"Expected replay_end frame after replay, got: {replay_end}"
            assert replay_end.get("turns") == turns_before, (
                f"Resumed session should report same turn count: expected {turns_before}, got {replay_end.get('turns')}"
            )

            # Session should still be playable after resume
            ws.send_json({"type": "advance", "text": "I look around"})
            advance_event = ws.receive_json()
            advance_turn_end = ws.receive_json()

            assert advance_event.get("type") == "event", "Expected AI event after advance"
            assert advance_turn_end.get("turns") == turns_before + 1, (
                f"Expected turns={turns_before + 1} after advance, got {advance_turn_end.get('turns')}"
            )


@pytest.mark.xfail(reason="pending run config refactoring")
@pytest.mark.parametrize("game", ALL_GAMES)
async def test_max_turns_override_stops_game(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Game should stop when max_turns run config override is reached."""
    assert False


@pytest.mark.xfail(reason="pending run config refactoring")
@pytest.mark.parametrize("game", ALL_GAMES)
async def test_max_runtime_override_stops_game(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Game should stop when max_runtime_seconds run config override is reached."""
    assert False


@pytest.mark.xfail(reason="pending run config refactoring")
@pytest.mark.parametrize("game", ALL_GAMES)
async def test_player_triggered_evals_configurable(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Player-triggered evaluations should be enabled/disabled per run config."""
    assert False


@pytest.mark.xfail(reason="pending run config refactoring")
@pytest.mark.parametrize("game", ALL_GAMES)
async def test_expose_overrides_available(game, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Game should expose all documented overrides via the run config interface."""
    assert False
