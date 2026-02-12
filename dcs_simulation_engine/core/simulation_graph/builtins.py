"""Builtin simulation graph node functions."""

import re
from typing import Any, Dict, List, Set, Tuple, Union

from jinja2.sandbox import SandboxedEnvironment
from loguru import logger
from tomlkit import key

from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import (
    SimulationGraphState,
)

JSONType = Union[
    Dict[str, Any], List[Any], Tuple[Any, ...], Set[Any], str, int, float, bool, None
]

# Use standard SandboxedEnvironment which allows dict attribute access (e.g., pc.hid)
# unlike LangChain's _RestrictedSandboxedEnvironment which blocks it
_jinja_env = SandboxedEnvironment()


def _render_any(value: JSONType, render_kwargs: dict[str, Any]) -> JSONType:
    """Recursively render Jinja2-style templates inside any supported data structure.

    - If `value` is a string containing Jinja syntax (`{{ ... }}` or `{% ... %}`),
      it is rendered using the provided context.
    - If `value` is a dict, list, tuple, or set, rendering is applied recursively.
    - All other types are returned untouched.

    Args:
        value: The value to inspect and possibly render.
        render_kwargs: Data used to render Jinja templates.

    Returns:
        A new structure with rendered values, preserving the original types.
    """
    # Render strings that look like Jinja templates
    if isinstance(value, str) and ("{{" in value or "{%" in value):
        tmpl = _jinja_env.from_string(value)
        return tmpl.render(**render_kwargs)

    # Recurse into common containers
    if isinstance(value, dict):
        return {k: _render_any(v, render_kwargs) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_any(v, render_kwargs) for v in value]
    if isinstance(value, tuple):
        return tuple(_render_any(v, render_kwargs) for v in value)
    if isinstance(value, set):
        return {_render_any(v, render_kwargs) for v in value}

    return value  # Base case: unchanged


def update_state(
    state: SimulationGraphState, context: ContextSchema, state_updates: dict[str, Any]
) -> dict[str, Any]:
    """Builtin update_state node function.

    Takes a dictionary of state field updates and applies them to the simulation state.
    """
    render_kwargs = {**state, "pc": context["pc"], "npc": context["npc"]}
    for state_key, state_val in state_updates.items():
        if state_key not in state:
            logger.error(f"State update key '{state_key}' not in state schema.")
            raise KeyError(
                f"State update key '{key}' not in state schema. Update state_updates."
            )
        val = _render_any(state_val, render_kwargs)
        state_updates[state_key] = val
    return state_updates


def raise_error(
    state: SimulationGraphState, context: ContextSchema, message: str
) -> None:
    """Builtin error node function.

    Takes an error message string and raises an error.
    """
    # TODO: pre-release - notify user? Update state? end-game reason?
    #  update end game reason?
    # Issue a special message?
    # render message from state
    tmpl = _jinja_env.from_string(message)
    rendered_message = tmpl.render(
        **{**state, "pc": context["pc"], "npc": context["npc"]}
    )
    logger.error(f"Error node called with message: {rendered_message}")
    raise RuntimeError(rendered_message)


def command_filter(
    state: SimulationGraphState, context: ContextSchema, command_handlers: dict
) -> dict[str, Any]:
    """Builtin command filter node function."""
    # Check state.event_draft for command pattern (e.g., "/help" or "\help")
    user_input = state.get("user_input")
    if not user_input:
        logger.warning("Command filter called with no user input.")
        return {}  # no draft, no state updates

    event = user_input.get("content") or ""
    # regex: start of string, slash or backslash, one or more word chars or dash
    m = re.match(r"^[\\/](?P<cmd>[\w-]+)\b", event.strip())
    if not m:
        logger.warning("No command found in user input for command_filter.")
        return {}  # no command found, no state updates

    command = m.group("cmd")
    if command_handlers.get(command) is None:
        logger.warning(f"Command '{command}' not handled in command_handler.")
        return {}  # command not handled, no state updates

    # command_handler is a dict of state updates
    command_handler = command_handlers[command]
    state_updates: dict[str, Any] = {
        "user_input": None,  # clear draft by default
    }
    render_kwargs = {
        **state,
        "pc": context["pc"],
        "npc": context["npc"],
        "command": command,
    }
    for state_key, state_val in command_handler.items():
        if state_key not in state:
            logger.error(f"Command handler key '{state_key}' not in state schema.")
            raise KeyError(
                f"Command handler key '{key}' not in state schema. Update handler."
            )
        val = _render_any(state_val, render_kwargs)
        state_updates[state_key] = val
    logger.debug(
        f"Command '{command}' matched; applying state updates: {state_updates}."
    )
    return state_updates


def form(
    state: SimulationGraphState, context: ContextSchema, form_name: str
) -> dict[str, Any]:
    """Builtin form node function.

    Takes a form definition and collects user responses to each question in the form.
    """
    forms = state["forms"]

    if forms is None:
        raise ValueError("No forms defined in state.")
    if form_name not in forms:
        raise KeyError(f"Form '{form_name}' not in forms {forms.keys()}.")

    form = forms[form_name]
    questions = form["questions"]

    def first_unanswered(start_idx: int = 0) -> int | None:
        """Return index of first unanswered question starting from start_idx."""
        for i in range(start_idx, len(questions)):
            if not questions[i].get("answer"):
                return i
        return None

    idx = first_unanswered(0)

    # If there is a user input, use it to answer the current unanswered question
    answer_draft: dict = state.get("user_input")
    if idx is not None and answer_draft and answer_draft.get("type") == "user":
        answer_content = (answer_draft.get("content") or "").strip()
        if answer_content:
            questions[idx]["answer"] = answer_content
            # Move to the next unanswered after recording the answer
            idx = first_unanswered(idx + 1)

    # If all questions are now answered, exit
    if idx is None:
        return {
            "simulator_output": {
                "type": "info",
                "content": "Form Complete.",
            },
            "lifecycle": "EXIT",
            "exit_reason": "Game completed.",
            "forms": {form_name: form},
        }

    # Otherwise, render and return the next question
    raw_question = questions[idx]["text"]
    rendered_question = _render_any(
        raw_question,
        {
            **state,
            "pc": context["pc"],
            "npc": context["npc"],
        },
    )

    return {
        "simulator_output": {"type": "info", "content": rendered_question},
        "forms": {form_name: form},
    }
