"""Builtin simulation graph node functions."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from langchain_core.prompts import PromptTemplate
from loguru import logger
from tomlkit import key

from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import (
    SimulationGraphState,
)

JSONType = Union[
    Dict[str, Any], List[Any], Tuple[Any, ...], Set[Any], str, int, float, bool, None
]


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
        tmpl = PromptTemplate.from_template(value, template_format="jinja2")
        return tmpl.format(**render_kwargs)

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
    tmpl = PromptTemplate.from_template(message, template_format="jinja2")
    rendered_message = tmpl.format(
        **{**state, "pc": context["pc"], "npc": context["npc"]}
    )
    logger.error(f"Error node called with message: {rendered_message}")
    raise RuntimeError(rendered_message)


def command_filter(
    state: SimulationGraphState, context: ContextSchema, command_handlers: dict
) -> dict[str, Any]:
    """Builtin command filter node function."""
    # Check state.event_draft for command pattern (e.g., "/help" or "\help")
    draft = state.get("event_draft")
    if not draft:
        return {}  # no draft, no state updates

    event = draft.get("content") or ""
    # regex: start of string, slash or backslash, one or more word chars or dash
    m = re.match(r"^[\\/](?P<cmd>[\w-]+)\b", event.strip())
    if not m:
        return {}  # no command found, no state updates

    command = m.group("cmd")
    if command_handlers.get(command) is None:
        logger.warning(f"Command '{command}' not handled in command_handler.")
        return {}  # command not handled, no state updates

    # command_handler is a dict of state updates
    command_handler = command_handlers[command]
    state_updates: dict[str, Any] = {
        "event_draft": None,  # clear draft by default
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


def retry(
    state: SimulationGraphState,
    context: ContextSchema,
    retry_message: Optional[str] = None,
) -> dict[str, Any]:
    """Retry node function.

    - Increments retries for the current actor (user/system).
    - If actor is user: interrupt and replace draft with revised text.
    - If actor is system/agent: inject guidance as a system draft.
    """
    user_retry_budget = state["user_retry_budget"]  # Typed required
    user_retry_budget -= 1
    remaining = user_retry_budget

    # Jinja guidance
    if retry_message is None:
        retry_message = (
            "Please revise your action. Use /help if you need a rules refresher. "
            "Previous action: {{event_draft.content}} "
            "Invalid reason: {{invalid_reason}} "
            "{{remaining}} retries left."
        )
    tmpl = PromptTemplate.from_template(retry_message, template_format="jinja2")
    guidance = tmpl.format(
        **{**state, "pc": context["pc"], "npc": context["npc"], "remaining": remaining}
    )

    logger.debug(f"User retries remaining={remaining} ")
    return {
        "special_user_message": {"type": "info", "content": guidance},
        "invalid_reason": None,  # clear invalid reason on retry
        "user_retry_budget": user_retry_budget,
    }


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

    # If there is a user draft, use it to answer the current unanswered question
    answer_draft: dict = state.get("user_input")
    if idx is not None and answer_draft and answer_draft.get("type") == "user":
        answer_content = (answer_draft.get("content") or "").strip()
        if answer_content:
            questions[idx]["answer"] = answer_content
            # Move to the next unanswered after recording the answer
            idx = first_unanswered(idx + 1)

    # If all questions are now answered, exit
    if idx is None:
        return {"lifecycle": "EXIT", "forms": {form_name: form}}

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
