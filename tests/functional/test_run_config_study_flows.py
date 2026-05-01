"""API flows for registered study-style example run configs."""

import asyncio

import pytest
from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
from tests.functional.example_run_config_helpers import (
    auth_headers,
    choose_or_locked_assignment,
    create_run_session,
    example_client,
    load_run_config,
    register_player,
    run_setup,
    submit_pending_group,
)

pytestmark = pytest.mark.functional


def test_benchmark_humans_auto_assigns_and_creates_session(patch_llm_client, async_mongo_provider) -> None:
    """Benchmark humans should move from entry forms through automatic assignments to outtake."""
    _ = patch_llm_client
    config = load_run_config("benchmark-humans")
    strategy = get_assignment_strategy(config.assignment_strategy.strategy)
    max_assignments = strategy.max_assignments_per_player(config=config)

    with example_client(async_mongo_provider, config) as client:
        auth_payload = register_player(client)
        headers = auth_headers(auth_payload)

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["reason"] == "pending_forms"
        submit_pending_group(client, headers, setup_payload, event="before_all_assignments")

        sessions = []
        for _index in range(max_assignments):
            setup_payload = run_setup(client, headers)
            assert setup_payload["next_assignment"]["mode"] == "locked"
            assignment = setup_payload["current_assignment"]
            sessions.append(create_run_session(client, headers, assignment_id=assignment["assignment_id"]))

            asyncio.run(
                async_mongo_provider.update_assignment_status(
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                )
            )

        setup_payload = run_setup(client, headers)
        assert setup_payload["assignment_completed"] is True
        assert "after_all_assignments" in {group["trigger"]["event"] for group in setup_payload["pending_form_groups"]}
        submit_pending_group(client, headers, setup_payload, event="after_all_assignments")
        final_setup = run_setup(client, headers)

    assert all(session["session_id"] for session in sessions)
    assert final_setup["pending_form_groups"] == []
    assert final_setup["assignment_completed"] is True
    assert config.assignment_strategy.strategy == "next_incomplete_combination"


def test_training_choice_flow_is_teamwork_only(patch_llm_client, async_mongo_provider) -> None:
    """Training should collect consent, expose only Teamwork options, and create a session."""
    _ = patch_llm_client
    config = load_run_config("training")

    with example_client(async_mongo_provider, config) as client:
        auth_payload = register_player(client)
        headers = auth_headers(auth_payload)

        setup_payload = run_setup(client, headers)
        submit_pending_group(client, headers, setup_payload, event="before_all_assignments")

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["mode"] == "choice"
        assert {option["game_name"] for option in setup_payload["eligible_assignment_options"]} == {"Teamwork"}

        assignment = choose_or_locked_assignment(client, headers, setup_payload)
        session = create_run_session(client, headers, assignment_id=assignment["assignment_id"])

    assert assignment["game_name"] == "Teamwork"
    assert session["session_id"]


def test_expert_evaluation_collects_expertise_and_stores_batch_assignment(
    patch_llm_client,
    async_mongo_provider,
) -> None:
    """Expert evaluation should use expertise forms before creating a batched assignment."""
    _ = patch_llm_client
    config = load_run_config("expert-evaluation")

    with example_client(async_mongo_provider, config) as client:
        auth_payload = register_player(client)
        headers = auth_headers(auth_payload)

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["reason"] == "pending_forms"
        submit_pending_group(client, headers, setup_payload, event="before_all_assignments")

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["mode"] == "locked"
        assignment = setup_payload["current_assignment"]
        session = create_run_session(client, headers, assignment_id=assignment["assignment_id"])

        stored_assignment = asyncio.run(async_mongo_provider.get_assignment(assignment_id=assignment["assignment_id"]))

    assert session["session_id"]
    assert stored_assignment is not None
    assert stored_assignment.data["batch_id"]
    assert stored_assignment.data["batch_npc_hid"] == assignment["npc_hid"]


def test_benchmark_ai_boots_without_human_participant_flow(async_mongo_provider) -> None:
    """Benchmark AI is covered as an API-startable model-player run only."""
    config = load_run_config("benchmark-ai")

    with example_client(async_mongo_provider, config) as client:
        server_config = client.get("/api/server/config")

    assert server_config.status_code == 200
    assert server_config.json()["default_run_name"] == config.name
    assert config.has_model_players is True
    assert config.players.humans.all is False
