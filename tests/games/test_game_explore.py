"""Tests for the Explore game."""

import pytest
from langgraph.types import Command
from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager
from tests._exploratory.langraph_inners import AIMessage

state_tests = {
    "initial_state": {
        "valid": [
            {
                "game": "explore",
                "pc_choice": "human-normative",
                "npc_choice": "flatworm",
            },
            {"game": "explore", "pc_choice": None, "npc_choice": None},
        ],
        "invalid": [
            {
                "game": "explore",
                "pc_choice": "unknown-pc",
                "npc_choice": "flatworm",
                "reason": "nonexistent pc_choice",
            },
            {
                "game": "explore",
                "pc_choice": "flatworm",
                "npc_choice": "human-normative",
                "reason": "pc_choice has to have human-like cognition",
            },
            {
                "game": "explore",
                "pc_choice": "unknown-pc",
                "npc_choice": "flatworm",
                "reason": "nonexistent pc_choice",
            },
        ],
    },
}


def _case_id(prefix: str, idx: int, case: dict) -> str:
    """Readable IDs in test output without changing your data shape."""
    reason = case.get("reason")
    tail = (reason or f"case-{idx}").replace(" ", "_")
    return f"{prefix}-{tail}"


@pytest.mark.unit
def test_initial_states_valid() -> None:
    """Test that valid initial states create runs successfully."""
    for i, kwargs in enumerate(state_tests["initial_state"]["valid"]):  # type: ignore[arg-type]
        run = RunManager.create(**kwargs)
        assert run is not None, _case_id("valid", i, kwargs)
        assert run.state is not None, _case_id("valid", i, kwargs)
        assert run.state["lifecycle"] == "INIT", _case_id("valid", i, kwargs)


@pytest.mark.unit
def test_initial_states_invalid() -> None:
    """Test that invalid initial states raise exceptions."""
    for i, case in enumerate(state_tests["initial_state"]["invalid"]):  # type: ignore[arg-type]
        kwargs = {k: v for k, v in case.items() if k != "reason"}
        with pytest.raises(
            Exception
        ):  # tighten later if engine exposes a specific error
            RunManager.create(**kwargs)


@pytest.fixture
def run() -> RunManager:
    """Fixture to create a RunManager for Explore game."""
    run = RunManager.create(
        game="explore", pc_choice="human-normative", npc_choice="flatworm"
    )
    assert run is not None
    return run


@pytest.mark.slow
def test_invalid_user_input(run: RunManager) -> None:
    """Test handling of invalid user input in the Explore game."""
    logger.warning(
        "Game flow tests make real graph calls including outgoing"
        " API calls to models; expect longer runtimes."
    )
    assert run.state is not None
    cfg = {"configurable": {"thread_id": "test-thread"}}
    run.state["lifecycle"] = "UPDATE"
    run.state["retry_limits"]["user"] = 2
    run.state["retries"]["user"] = 1
    run.state["events"] = [
        {
            "type": "simulator",
            "content": "You enter a new space. In this space there is a table with a glass tank on it.",
        }
    ]
    run.state["event_draft"] = {"role": "user", "content": "I break the game."}
    # invoke must be called with cfg so graph thread_id is set and interrupts work
    res1 = run.graph.cgraph.invoke(run.state, cfg)
    logger.debug(f"First invalid user input response: {res1}")
    # new retry count doesn't update until next call
    assert res1["retries"]["user"] == 1
    assert res1["__interrupt__"]
    # user still inputs breaking input
    revised = res1["event_draft"]["content"]
    # interupts are resolved by passing through Command
    res2 = run.graph.cgraph.invoke(Command(resume=revised), config=cfg)
    logger.debug(f"Second invalid user input response: {res2}")
    # should have incremented retry count
    assert res2["retries"]["user"] == 2
    # should end game due to user failures
    assert res2["lifecycle"] == "EXIT"
    assert res2["special_message"] is not None


@pytest.mark.slow
def test_invalid_system_input(run: RunManager) -> None:
    """Test handling of invalid system input in the Explore game."""
    logger.warning(
        "Game flow tests make real graph calls including outgoing \
                 API calls to models; expect longer runtimes."
    )
    assert run.state is not None
    cfg = {"configurable": {"thread_id": "test-thread"}}
    run.state["lifecycle"] = "UPDATE"
    run.state["retry_limits"]["ai"] = 2
    run.state["retries"]["ai"] = 1
    run.state["event_draft"] = {"type": "ai", "content": "I turn invisible."}
    res1 = run.graph.cgraph.invoke(run.state, config=cfg)
    logger.debug(f"First invalid system input response: {res1}")
    assert res1["retries"]["ai"] == 2


@pytest.mark.slow
def test_valid_user_input(run: RunManager) -> None:
    """Test handling of valid user input in the Explore game."""
    logger.warning(
        "Game flow tests make real graph calls including outgoing \
                 API calls to models; expect longer runtimes."
    )
    assert run.state is not None
    conf = {"configurable": {"thread_id": "test-thread"}}
    run.state["lifecycle"] = "UPDATE"
    run.state["events"] = [
        AIMessage(
            "You enter a new space. In this space there is a table with a glass tank on it."
        )
    ]
    run.state["event_draft"] = {"role": "user", "content": "I look around."}
    res = run.graph.cgraph.invoke(run.state, config=conf)
    logger.debug(f"Valid user input response: {res}")
    # output should include a user and system turn
    assert res["lifecycle"] == "UPDATE"
    assert res["special_message"] in ("", None)  # should not have special message
    assert res["invalid_reason"] in ("", None)  # should be valid
    # assert res["message_draft"] is None  # should have cleared draft
    assert len(res["events"]) == 3
