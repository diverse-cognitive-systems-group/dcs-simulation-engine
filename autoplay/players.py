"""Player adapters for autoplay."""

import importlib.util
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import httpx
from autoplay.types import PlayerContext
from loguru import logger

_OPENROUTER_CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODEL_PLAYER_SYSTEM_PROMPT = (
    "You are playing a roleplaying game as the player character. "
    "The visible game context may include info messages that explain the objective, available commands, and how to finish. "
    "Read those messages carefully before choosing an action. "
    "If the game exposes /help, you may use it to request instructions. "
    "Return exactly one next player input. "
    "Do not include explanation or commentary."
)


class ApiPlayer(Protocol):
    """A client-side player that produces the next API-visible input."""

    model_id: str

    async def next_input(self, context: PlayerContext) -> str:
        """Return exactly one player message or slash command."""


class ScriptedPlayer:
    """Deterministic player used by tests and local harness smoke runs."""

    def __init__(
        self,
        *,
        model_id: str = "scripted",
        scripts_by_game: dict[str, list[str]] | None = None,
        default_script: list[str] | None = None,
    ) -> None:
        """Create a scripted player from per-game or default responses."""
        self.model_id = model_id
        self._scripts_by_game = {key.lower(): list(value) for key, value in (scripts_by_game or {}).items()}
        self._default_script = list(default_script or ["/finish"])
        self._positions: dict[str, int] = {}

    async def next_input(self, context: PlayerContext) -> str:
        """Return the next scripted input for the current game."""
        game_name = str(context.assignment.get("game_name") or "").lower()
        script = self._scripts_by_game.get(game_name, self._default_script)
        key = context.assignment.get("assignment_id") or context.session_id
        index = self._positions.get(str(key), 0)
        self._positions[str(key)] = index + 1
        if index < len(script):
            return script[index]
        return script[-1]


class OpenRouterPlayer:
    """OpenRouter-backed API player."""

    def __init__(self, *, model_id: str, timeout: float | None = None) -> None:
        """Create an OpenRouter-backed player for one model id."""
        if not model_id.strip():
            raise ValueError("OpenRouter model id must be non-empty.")
        self.model_id = f"openrouter:{model_id.strip()}"
        self._openrouter_model = model_id.strip()
        self._timeout = timeout
        self.system_prompt = MODEL_PLAYER_SYSTEM_PROMPT

    async def next_input(self, context: PlayerContext) -> str:
        """Ask the configured OpenRouter model for one player input."""
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter API players.")

        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {"role": "user", "content": _format_context(context)},
        ]
        payload = {"model": self._openrouter_model, "messages": messages, "max_completion_tokens": 1024}
        logger.info(
            "OpenRouter request: model={} session={} turn={} history_events={}",
            self.model_id,
            context.session_id,
            context.turns,
            len(context.history),
        )
        logger.debug("OpenRouter payload:\n{}", json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True))
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                _OPENROUTER_CHAT_ENDPOINT,
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return str(content).strip()


class PythonModulePlayer:
    """Python-file-backed API player."""

    def __init__(self, *, path: Path) -> None:
        """Create a player from a Python module that exposes decide(context)."""
        self.path = path.expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Python player file not found: {self.path}")
        self.model_id = f"python:{self.path}"
        self._decide = self._load_decide(self.path)

    async def next_input(self, context: PlayerContext) -> str:
        """Call the module's decide(context) function."""
        result = self._decide(_context_payload(context))
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        text = str(result).strip()
        if not text:
            raise ValueError(f"Python player {self.path} returned an empty input.")
        return text

    def _load_decide(self, path: Path) -> Callable[[dict[str, Any]], str | Awaitable[str]]:
        module_name = f"dcs_api_player_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not load Python player module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        decide = getattr(module, "decide", None)
        if not callable(decide):
            raise ValueError(f"Python player module must define decide(context): {path}")
        return decide


def player_from_spec(spec: str) -> ApiPlayer:
    """Build an API player from a CLI-style provider spec."""
    provider, separator, value = spec.partition(":")
    provider = provider.strip().lower()
    value = value.strip()
    if not separator or not provider or not value:
        raise ValueError(f"Invalid player spec: {spec!r}")
    if provider == "openrouter":
        return OpenRouterPlayer(model_id=value)
    if provider == "python":
        return PythonModulePlayer(path=Path(value))
    raise ValueError(f"Unsupported player provider: {provider}")


def _format_context(context: PlayerContext) -> str:
    payload = _context_payload(context)
    return json.dumps(payload, indent=2, ensure_ascii=True)


def _context_payload(context: PlayerContext) -> dict[str, Any]:
    return {
        "run_name": context.run_name,
        "player_id": context.player_id,
        "model_id": context.model_id,
        "assignment": context.assignment,
        "session_id": context.session_id,
        "session_meta": context.session_meta,
        "turns": context.turns,
        "last_error": context.last_error,
        "history": [
            {
                "role": turn.role,
                "event_type": turn.event_type,
                "content": turn.content,
                "failure_type": turn.failure_type,
            }
            for turn in context.history
        ],
    }
