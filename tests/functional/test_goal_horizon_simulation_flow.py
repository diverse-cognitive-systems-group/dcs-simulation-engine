"""Functional tests for goal-horizon game simulation flow with mocked LLMs.

This test suite validates the goal-horizon game's mechanics:
1. Consent-required player access
2. Minimal graph configuration (START → END)
3. Lifecycle transitions and state persistence

Tests use mocked LLMs to avoid external API dependencies.

TODO: The goal-horizon.yml game config has an invalid MongoDB query syntax for NPC
character constraints (`$ne` at top level instead of field level). This prevents
testing NPC constraint validation with mongomock. Fix the game config and add
NPC constraint tests when resolved. See games/goal-horizon.yml:79-82.
"""

import pytest
from bson import ObjectId
from pathlib import Path
from unittest.mock import patch

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.core.run_manager import RunManager


# Test player ID for goal-horizon tests (requires consent)
TEST_PLAYER_ID = ObjectId()

# Path to goal-horizon game config
GOAL_HORIZON_CONFIG = Path(__file__).parent.parent.parent / "games" / "goal-horizon.yml"


@pytest.fixture
def patch_get_valid_characters():
    """Patch get_valid_characters to bypass invalid MongoDB NPC query.

    The goal-horizon.yml config has invalid MongoDB syntax (`$ne` at top level
    instead of field level) that causes mongomock to fail. This fixture returns
    mock character lists that would be returned if the query were valid.

    TODO: Remove this fixture when games/goal-horizon.yml:79-82 is fixed.
    """
    def mock_get_valid_characters(self, player_id=None):
        # Return all characters for PC (open constraint)
        # Return non-human-normative characters for NPC (simulating $ne constraint)
        # Format: list of tuples (formatted_name, hid)
        all_chars = ["flatworm", "human-normative", "octopus", "dolphin",
                     "corvid", "great-ape", "elephant", "canine", "feline"]
        pc_chars = [(c, c) for c in all_chars]  # (formatted, hid) tuples
        npc_chars = [(c, c) for c in all_chars if c != "human-normative"]
        return pc_chars, npc_chars

    with patch(
        "dcs_simulation_engine.core.game_config.GameConfig.get_valid_characters",
        mock_get_valid_characters
    ):
        yield


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state):
    """Seed a player with consent signature for goal-horizon game access.

    The goal-horizon game requires players to have consent_signature.answer
    in their player document. This fixture creates such a player.
    """
    db = dbh.get_db()
    db[dbh.PLAYERS_COL].insert_one({
        "_id": TEST_PLAYER_ID,
        "consent_signature": {
            "answer": ["I confirm that the information I have provided is true..."]
        },
        "full_name": "Test Player",
        "email": "test@example.com",
    })
    yield


@pytest.mark.functional
def test_goal_horizon_initialization(patch_llm_client, patch_get_valid_characters, _isolate_db_state):
    """Test goal-horizon game initializes correctly with RunManager.

    Verifies:
    - RunManager.create works with goal-horizon game config
    - Initial lifecycle is ENTER
    - Initial history is empty

    Note: Uses patch_get_valid_characters to bypass NPC constraint validation
    which has invalid MongoDB syntax in the game config. See module docstring.
    """
    run = RunManager.create(
        game=GOAL_HORIZON_CONFIG,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"
    assert len(run.state["history"]) == 0, "Initial history should be empty"


@pytest.mark.functional
def test_goal_horizon_minimal_graph_step(patch_llm_client, patch_get_valid_characters, _isolate_db_state):
    """Test minimal graph (START → END) executes without errors.

    Verifies:
    - run.step("") executes the minimal graph flow
    - No errors from missing simulation subgraph
    - Run state exists after step
    """
    run = RunManager.create(
        game=GOAL_HORIZON_CONFIG,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"

    # Execute step - minimal graph goes START → END
    events = list(run.step(""))

    # The minimal graph should complete without errors
    # Lifecycle may remain ENTER or transition depending on graph behavior
    # Key assertion: no exception was raised
    assert run.state is not None, "Run state should exist after step"


@pytest.mark.functional
def test_goal_horizon_exit_and_save(patch_llm_client, patch_get_valid_characters, _isolate_db_state):
    """Test goal-horizon game runs can be exited and saved to database.

    Verifies:
    - run.exit() transitions lifecycle to EXIT
    - run.save() returns non-None path after exit
    """
    run = RunManager.create(
        game=GOAL_HORIZON_CONFIG,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute initial step
    list(run.step(""))

    # Exit and save
    run.exit(reason="test complete")
    assert run.state["lifecycle"] == "EXIT", "Lifecycle should be EXIT after exit()"

    saved = run.save()
    assert saved is not None, "run.save() should return a path on success"
