"""API end-to-end flow tests for the real usability example run config."""

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


def test_usability_run_forms_assignments_and_sessions_flow(patch_llm_client, async_mongo_provider) -> None:
    """Usability should gate assignment by forms, allow choice, and collect post/outtake feedback."""
    _ = patch_llm_client
    config = load_run_config("usability")

    with example_client(async_mongo_provider, config) as client:
        auth_payload = register_player(client)
        headers = auth_headers(auth_payload)

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["mode"] == "blocked"
        assert setup_payload["next_assignment"]["reason"] == "pending_forms"
        assert {group["trigger"]["event"] for group in setup_payload["pending_form_groups"]} == {"before_all_assignments"}

        submit_pending_group(client, headers, setup_payload, event="before_all_assignments")

        setup_payload = run_setup(client, headers)
        assert setup_payload["next_assignment"]["mode"] == "choice"
        assert setup_payload["eligible_assignment_options"]

        completed = 0
        strategy = get_assignment_strategy(config.assignment_strategy.strategy)
        max_assignments = strategy.max_assignments_per_player(config=config)
        while completed < max_assignments:
            assignment = choose_or_locked_assignment(client, headers, setup_payload)
            create_run_session(client, headers, assignment_id=assignment["assignment_id"])

            asyncio.run(
                async_mongo_provider.update_assignment_status(
                    assignment_id=assignment["assignment_id"],
                    status="completed",
                )
            )
            completed += 1

            setup_payload = run_setup(client, headers)
            assert setup_payload["next_assignment"]["mode"] == "blocked"
            assert setup_payload["next_assignment"]["reason"] == "pending_assignment_forms"
            assert "after_assignment" in {group["trigger"]["event"] for group in setup_payload["pending_form_groups"]}
            submit_pending_group(client, headers, setup_payload, event="after_assignment")

            setup_payload = run_setup(client, headers)

        assert setup_payload["assignment_completed"] is True
        assert setup_payload["next_assignment"]["mode"] == "none"
        assert setup_payload["next_assignment"]["reason"] == "complete"
        assert "after_all_assignments" in {group["trigger"]["event"] for group in setup_payload["pending_form_groups"]}

        submit_pending_group(client, headers, setup_payload, event="after_all_assignments")
        final_setup = run_setup(client, headers)

    assert final_setup["assignment_completed"] is True
    assert final_setup["pending_form_groups"] == []
    assert final_setup["next_assignment"]["mode"] == "none"
