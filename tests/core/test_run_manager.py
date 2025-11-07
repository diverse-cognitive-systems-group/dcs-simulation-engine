"""Tests for the RunManager module."""

import pytest
from langchain_core.messages import AIMessage
from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.core.simulation_graph import SimulationGraph
from dcs_simulation_engine.helpers import database_helpers as dbh

# TODO: mock then mark as unit


def test_init_from_create(run: RunManager) -> None:
    """Should initialize RunManager."""
    assert run is not None
    assert run.state is not None
    assert run.context["pc"] is not None
    assert run.context["npc"] is not None
    assert run.state["events"] is not None

    assert run.graph is not None
    assert isinstance(run.graph, SimulationGraph)


def test_save_run_to_database(persistant_run: RunManager) -> None:
    """Should save state on stop."""
    run = persistant_run
    assert run is not None
    logger.debug(f"Run state before stopping: {run}")
    assert run.player_id is not None
    assert run.state is not None
    run.exit(reason="unit test stop")
    assert run.exited
    assert run.exit_reason == "unit test stop"
    # Check that the doc is in the database
    db = dbh.get_db()
    doc = db[dbh.RUNS_COL].find_one({"player_id": run.player_id})
    assert doc is not None
    assert doc["exit_reason"] == "unit test stop"


@pytest.mark.slow
def test_first_step(run: RunManager) -> None:
    """Test with no message in state.

    - should use scene_setup_agent system prompt template.
    """
    # TODO: pre-oss - mock these LLM calls
    logger.warning("This test will make actual LLM calls!")
    assert run is not None
    print(f"Initial state: {run.state}")
    run.step()  # returns and updates self.state with next state
    print(f"New state: {run.state}")
    assert run.state is not None
    assert len(run.state["messages"]) == 0
    # TODO: messages conent should contain "SETUP_SCENE"


@pytest.mark.slow
def test_continuation_steps(run: RunManager) -> None:
    """Test with existing messages.

    - should use scene_continuation_agent system prompt template.
    """
    # TODO: pre-oss - mock these LLM calls
    logger.warning("This test will make actual LLM calls!")
    run._ensure_state()
    assert run.state is not None
    run.state.get("messages", []).append(AIMessage("A beautiful day in the park."))  # type: ignore
    print(f"Initial state: {run.state}")
    # append a message so it uses the scene continuation agent next
    run.step()  # second step should use continuation agent
    print(f"State after second step: {run.state}")
    assert len(run.state.get("messages", [])) == 2
    # the last message should say "CONTINUE_SCENE"
    assert run.state.get("messages", [])[-1].content == "CONTINUE_SCENE"


@pytest.mark.slow
def test_stops_on_condition(run: RunManager) -> None:
    """Test with stop and save after first step."""
    # TODO: pre-oss - mock these LLM calls
    logger.warning("This test will make actual LLM calls!")
    assert run is not None
    print(f"Initial state: {run.state}")
    run.step()  # returns and updates self.state with next state
    print(f"New state: {run.state}")
    assert run.state is not None
    assert len(run.state.get("messages", [])) == 0
    assert (
        run.state.get("agent_artifacts", {}).get("scene_setup_agent", {}).get("text")
        == "SETUP_SCENE"
    )
    run.stop(reason="test complete")
    assert run.stopped
    assert run.stop_reason == "test complete"
