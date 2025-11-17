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
        "user_input": "",
        "user_validation_message": None,
        "response_message": None,
        "final_message": None,
        "retries": {"user": 0, "ai": 0},
        "retry_limits": {"user": 3, "ai": 3},
        "forms": None,
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
        logger.error("Invalid SimulationState: %s", e)
        raise


class SpecialUserMessage(TypedDict):
    """Special user message structure."""

    type: Literal["info", "warning", "error"]
    content: str


class Form(TypedDict):
    """Form structure for collecting user input."""

    questions: list[FormQuestion]


class FormQuestion(TypedDict):
    """Form question structure."""

    key: str
    text: str
    answer: str


MessageType = Literal["info", "error", "ai", "user"]


class SimulationMessage(TypedDict):
    """Simulation message structure."""

    type: MessageType
    content: str


class Retries(TypedDict):
    """Retry limits for players.

    Note: using user and ai makes it easier to use
    built-in openrouter and langgraph message functionalities

    """

    user: int  # player (pc)
    ai: int  # simulator (npc)


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
    retries: Retries
    retry_limits: Retries

    # Message management
    history: Annotated[list[BaseMessage], add_messages]
    user_input: str

    user_validation_message: Optional[SimulationMessage]
    response_message: Optional[SimulationMessage]
    final_message: Optional[SimulationMessage]

    # Data collection management
    forms: Optional[dict[str, Form]]


# Used for validation and parsing
StateAdapter = TypeAdapter(SimulationGraphState)
