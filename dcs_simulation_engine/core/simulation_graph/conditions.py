"""Condition evaluation utilities for sim graph routing."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from loguru import logger


def eval_condition(expr: str, state: Mapping[str, Any]) -> bool:
    """Evaluate simple state expressions against `state`.

    Accepted examples:
      - "{{ state.goal_guessed == true }}"
      - "{{ state.turns > 3 }}"
      - "state.goal_guessed"
    NOTE: Uses a restricted eval over the `state` mapping.
    """
    if not expr:
        return False
    s = expr.strip()
    if s.startswith("{{") and s.endswith("}}"):
        s = s[2:-2].strip()

    # Normalize booleans/null to Python
    s = (
        s.replace(" true", " True")
        .replace("true", "True")
        .replace(" false", " False")
        .replace("false", "False")
        .replace(" null", " None")
        .replace("null", "None")
    )

    # expose *only* safe functions you want to allow
    safe_globals: dict[str, Any] = {
        "__builtins__": {},
        "len": len,
        "any": any,
        "all": all,
        "min": min,
        "max": max,
    }
    # allow both "state.*" and bare "messages"
    safe_locals: dict[str, Any] = {
        "state": state,
    }

    try:
        result = eval(s, safe_globals, safe_locals)  # noqa: S307
        logger.debug(f"Condition eval {bool(result)} for {expr}")
        return bool(result)
    except Exception as e:
        logger.error(f"Condition eval error for {expr} using eval with source:\n{s}. Error: {e}")
        return False


def last_text(state: Mapping[str, Any]) -> str:
    """Get the text of the last message in state['messages'], if any."""
    msgs = state.get("messages") or []
    try:
        last = msgs[-1]
        if hasattr(last, "content"):
            return last.content or ""
        if isinstance(last, dict):
            return last.get("content") or ""
    except Exception:
        pass
    return ""


def predicate(expr: Optional[str], state: Mapping[str, Any]) -> bool:
    """Predicate function for routing conditions.

    Supported inline predicates:
    - "len(messages) == 0"
    - "reply_contains('yes')"   # case-insensitive
    - any simple "state.*" check handled by eval_condition
    """
    if not expr:  # treat missing as 'else'
        return True

    s = expr.strip()

    if s == "len(messages) == 0":
        return len(state.get("messages") or []) == 0

    if s.startswith("reply_contains(") and s.endswith(")"):
        arg = s[len("reply_contains(") : -1].strip()
        if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
            needle = arg[1:-1]
        else:
            needle = arg
        return needle.lower() in last_text(state).lower()

    try:
        res = eval_condition(s, state)
        return bool(res)
    except Exception:
        logger.exception(f"Error evaluating predicate expr: {expr}.")
        return False


# TODO: pre-release - add validation for condition expressions in build like we
#  did for node jinja evals in compile().
