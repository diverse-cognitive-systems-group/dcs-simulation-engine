"""Anonymous API flows for demo-style example run configs."""

import pytest
from tests.functional.example_run_config_helpers import (
    assert_authenticates,
    auth_headers,
    choose_or_locked_assignment,
    create_anonymous_player,
    create_run_session,
    example_client,
    load_run_config,
    run_setup,
)

pytestmark = pytest.mark.functional


@pytest.mark.parametrize("config_name", ["demo", "select-characters"])
def test_anonymous_choice_run_can_select_assignment_and_create_session(
    config_name: str,
    patch_llm_client,
    async_mongo_provider,
) -> None:
    """Anonymous example configs should expose choices and create run sessions."""
    _ = patch_llm_client
    config = load_run_config(config_name)

    with example_client(async_mongo_provider, config) as client:
        auth_payload = create_anonymous_player(client)
        assert_authenticates(client, auth_payload)
        headers = auth_headers(auth_payload)

        setup_payload = run_setup(client, headers)
        assert setup_payload["pending_form_groups"] == []
        assert setup_payload["next_assignment"]["mode"] == "choice"
        assert setup_payload["eligible_assignment_options"]

        configured_games = set(config.game_names)
        option_games = {option["game_name"] for option in setup_payload["eligible_assignment_options"]}
        assert option_games.issubset(configured_games)

        assignment = choose_or_locked_assignment(client, headers, setup_payload)
        session = create_run_session(client, headers, assignment_id=assignment["assignment_id"])

    assert session["session_id"]
