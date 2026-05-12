"""Functional tests for the autoplay client."""

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from autoplay import PlayerContext, PlayerHarness, ScriptedPlayer
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.core.run_config import RunConfig

pytestmark = pytest.mark.functional


_SCRIPTS_BY_GAME = {
    "Explore": ["/finish"],
    "Infer Intent": [
        "I greet them and ask what they are trying to do.",
        "/finish",
        "They seem focused on avoiding uncomfortable situations.",
        "High confidence.",
    ],
    "Goal Horizon": [
        "I ask what kinds of places they can comfortably navigate.",
        "/finish",
        "They seem limited by bright and crowded environments.",
        "Medium confidence.",
    ],
    "Foresight": [
        "I wave hello and predict they will answer cautiously.",
        "/finish",
    ],
    "Teamwork": [
        "I suggest we work together and ask what task we should coordinate on.",
        "/finish",
        "The hardest part was coordinating timing and communication.",
    ],
}


class InspectingPlayer:
    """Scripted player that records the contexts it receives."""

    def __init__(self, inputs: list[str]) -> None:
        """Store scripted inputs for later decisions."""
        self.model_id = "inspecting"
        self.inputs = list(inputs)
        self.contexts: list[PlayerContext] = []

    async def next_input(self, context: PlayerContext) -> str:
        """Record the context and return the next scripted input."""
        self.contexts.append(context)
        if self.inputs:
            return self.inputs.pop(0)
        return "/finish"


def _run_config(
    *,
    game_name: str = "Explore",
    registration_required: bool = False,
    allow_choice_if_multiple: bool = False,
    forms: list[dict] | None = None,
) -> RunConfig:
    overrides = {}
    if game_name != "Explore":
        overrides["show_final_score"] = False
    return RunConfig.model_validate(
        {
            "name": f"auto-play-{game_name.lower().replace(' ', '-')}",
            "description": "autoplay functional test run",
            "ui": {"registration_required": registration_required},
            "games": [{"name": game_name, "overrides": overrides}],
            "next_game_strategy": {
                "strategy": {
                    "id": "full_character_access",
                    "allow_choice_if_multiple": allow_choice_if_multiple,
                    "require_completion": True,
                    "max_assignments_per_player": 1,
                }
            },
            "forms": forms or [],
        }
    )


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@contextmanager
def _live_server(*, provider, run_config: RunConfig) -> Iterator[str]:
    port = _find_open_port()
    app = create_app(
        provider=provider,
        run_config=run_config,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        ws="websockets-sansio",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10.0
    try:
        while time.time() < deadline:
            try:
                response = httpx.get(f"{base_url}/healthz", timeout=0.25)
                if response.status_code == 200:
                    yield base_url
                    break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError(f"Timed out waiting for test server at {base_url}")
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


@pytest.mark.anyio
@pytest.mark.parametrize("game_name", sorted(_SCRIPTS_BY_GAME))
async def test_autoplay_completes_game_assignment(
    game_name: str,
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """Autoplay should play through complete backend assignments."""
    _ = patch_llm_client
    run_config = _run_config(game_name=game_name)
    player = ScriptedPlayer(
        model_id=f"scripted:{game_name}",
        scripts_by_game={game_name: _SCRIPTS_BY_GAME[game_name]},
    )

    with _live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        result = await PlayerHarness(base_url=base_url, player=player, max_turns_per_assignment=8).run()

    assert result.run_name == run_config.name
    assert result.player_id
    assert len(result.assignments) == 1
    assert result.assignments[0].game_name == game_name
    assert result.assignments[0].status == "completed"
    assert result.assignments[0].session_id


@pytest.mark.anyio
async def test_autoplay_selects_first_choice_assignment(
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """Choice-mode runs should be playable without engine internals."""
    _ = patch_llm_client
    run_config = _run_config(game_name="Explore", allow_choice_if_multiple=True)
    player = ScriptedPlayer(default_script=["/finish"])

    with _live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        result = await PlayerHarness(base_url=base_url, player=player).run()

    assert len(result.assignments) == 1
    assert result.assignments[0].status == "completed"


@pytest.mark.anyio
async def test_autoplay_fails_loudly_on_pending_forms(
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """The first harness version should not silently auto-submit study forms."""
    _ = patch_llm_client
    run_config = _run_config(
        game_name="Explore",
        forms=[
            {
                "name": "intake",
                "trigger": {"event": "before_all_assignments", "match": None},
                "questions": [
                    {
                        "answer_type": "string",
                        "key": "note",
                        "prompt": "Say something.",
                        "required": True,
                    }
                ],
            }
        ],
    )
    player = ScriptedPlayer(default_script=["/finish"])

    with _live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        with pytest.raises(RuntimeError, match="does not submit forms yet"):
            await PlayerHarness(base_url=base_url, player=player).run()


@pytest.mark.anyio
async def test_autoplay_player_context_includes_opening_info_and_simulator_events(
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """Model players should see the same opening guidance and scene a human sees."""
    _ = patch_llm_client
    run_config = _run_config(game_name="Explore")
    player = InspectingPlayer(inputs=["/finish"])

    with _live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        result = await PlayerHarness(base_url=base_url, player=player, max_turns_per_assignment=4).run()

    assert result.assignments[0].status == "completed"
    assert player.contexts, "autoplay should ask the player for at least one decision"
    first_context = player.contexts[0]
    assert any(turn.event_type == "info" and "/help" in turn.content for turn in first_context.history)
    assert any(turn.role == "simulator" and turn.event_type == "ai" and turn.content for turn in first_context.history)


@pytest.mark.anyio
async def test_autoplay_interrupts_assignment_at_max_turns(
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """Autoplay should stop an assignment when its turn budget is exhausted."""
    _ = patch_llm_client
    run_config = _run_config(game_name="Explore")
    player = ScriptedPlayer(default_script=["I keep looking around."])

    with _live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        result = await PlayerHarness(base_url=base_url, player=player, max_turns_per_assignment=2).run()

    assert len(result.assignments) == 1
    assert result.assignments[0].status == "interrupted"
    assert result.assignments[0].error == "max_turns_per_assignment reached: 2"


@pytest.mark.unit
def test_python_module_player_loads_decide_function(tmp_path: Path) -> None:
    """Python-backed players should load from a standalone client file."""
    player_path = tmp_path / "player.py"
    player_path.write_text(
        "def decide(context):\n    assert context['run_name']\n    return '/finish'\n",
        encoding="utf-8",
    )

    from autoplay import PythonModulePlayer

    player = PythonModulePlayer(path=player_path)

    assert player.model_id == f"python:{player_path.resolve()}"
