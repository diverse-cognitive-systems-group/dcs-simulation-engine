"""Graph state schema definition."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, cast

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from loguru import logger
from pydantic import TypeAdapter, ValidationError
from typing_extensions import (
    TypedDict,
)


def display_state_snapshot(state: dict[str, Any], preview_chars: int = 80) -> None:
    """Build a full state snapshot string and log it in one call."""
    parts: list[str] = []
    parts.append("State snapshot:")

    # Non-history keys
    for k, v in state.items():
        if k != "history":
            parts.append(f"{k}: {v}")

    # History length
    history = state.get("history", [])
    hist_len = len(history) if history else 0
    parts.append(f"history length: {hist_len}")

    # Preview last entry
    if hist_len > 0:
        last = history[-1]

        if isinstance(last, BaseMessage):
            content = last.content
        else:
            content = getattr(last, "content", None)

        if content:
            preview = content[:preview_chars].replace("\n", " ")
            parts.append(f"history[-1] preview ({preview_chars} chars): {preview}")

    # Log as a single message
    logger.debug("\n".join(parts))


def make_state(overrides: dict[str, Any] | None = None) -> SimulationGraphState:
    """Create a SimulationGraphState with sensible defaults and optional overrides."""
    overrides = dict(overrides or {})

    # Other defaults + warnings
    if "lifecycle" not in overrides:
        logger.warning("No lifecycle provided; defaulting to INIT.")
    if "retry_limits" not in overrides:
        logger.debug("No retry_limits provided; defaulting to {'user': 3, 'ai': 3}.")

    base: SimulationGraphState = {
        "lifecycle": "INIT",
        "exit_reason": "",
        "history": [],
        "user_input": None,
        "validator_response": None,
        "updater_response": None,
        "simulator_output": None,
        "user_retry_budget": 6,
        "forms": None,
        "scratchpad": None,
    }

    # Warn & drop unknown override keys
    # Prefer model fields if available (pydantic v2 or v1), else fall back to base keys.
    try:
        allowed_keys = set(
            getattr(StateAdapter, "model_fields", None)
            and StateAdapter.model_fields.keys()  # type: ignore
        ) or set(getattr(StateAdapter, "__fields__", {}).keys())
        if not allowed_keys:
            allowed_keys = set(base.keys())
    except Exception:
        allowed_keys = set(base.keys())

    unknown = set(overrides) - allowed_keys
    if unknown:
        logger.warning(
            "Unknown override key(s) ignored: %s", ", ".join(sorted(unknown))
        )
        for k in unknown:
            overrides.pop(k, None)

    state = cast(SimulationGraphState, {**base, **overrides})
    try:
        return cast(SimulationGraphState, StateAdapter.validate_python(state))
    except ValidationError as e:
        logger.error("Invalid SimulationGraphState: %s", e)
        raise


class Form(TypedDict):
    """Form structure for collecting user input."""

    questions: list[FormQuestion]


class FormQuestion(TypedDict):
    """Form question structure."""

    key: str
    text: str
    answer: str


MessageType = Literal["info", "error", "command", "warning", "ai", "user"]


class SimulationMessage(TypedDict):
    """Simulation message structure."""

    type: MessageType
    content: str


class SimulationGraphState(TypedDict, total=True):
    """Schema for the shared simulation state.

    A few langgraph functionality notes:
    - Langgraph graph is invoked with this overall state which is a TypedDict
    - Each node gets this state input and returns a dict with keys that langgraph
    adds/updates it with using the defined reducers. If no reducer is defined langgraph
      overwrites the key.

    """

    # Lifecycle management
    lifecycle: Literal["INIT", "ENTER", "UPDATE", "EXIT", "COMPLETE"]
    exit_reason: str
    user_retry_budget: int

    # Message management
    history: Annotated[list[BaseMessage], add_messages]
    user_input: Optional[SimulationMessage]
    simulator_output: Optional[SimulationMessage]

    # Intermediate processing messages from subgraph
    validator_response: Optional[SimulationMessage]
    updater_response: Optional[SimulationMessage]

    # Data collection management
    forms: Optional[dict[str, Form]]

    # Node scratchpad in case any reasoning, or additional state is needed
    scratchpad: Optional[dict[str, Any]]


# Used for validation and parsing
StateAdapter = TypeAdapter(SimulationGraphState)
