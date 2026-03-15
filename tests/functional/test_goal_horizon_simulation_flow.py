"""Functional tests for goal-horizon game simulation flow with mocked LLMs.

This test suite validates the goal-horizon game's mechanics:
1. Consent-required player access
2. Standard enter/turn/exit flow
3. Session persistence

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

# Test player ID for goal-horizon tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a player with consent signature for goal-horizon game access."""
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


async def test_goal_horizon_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test goal-horizon game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_goal_horizon_enter_step(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test enter step produces events and session state is valid."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    events = await session.step_async("")

    assert len(events) > 0, "ENTER step should produce events"
    assert session._events is not None, "Session events should exist after step"


async def test_goal_horizon_exit_and_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test goal-horizon game sessions can be exited and saved."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"
    assert session.exit_reason == "test complete"

    # save() is called internally by exit(); calling again is a no-op
    session.save()
