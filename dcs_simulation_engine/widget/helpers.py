"""Helper functions for widget."""

import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

import gradio as gr
from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.widget.constants import USER_FRIENDLY_EXC
from dcs_simulation_engine.widget.session_state import SessionState


def cleanup(state: gr.State) -> None:
    """Clean up resources associated with a session."""
    logger.debug("Cleaning up session resources")
    session_state: SessionState = state.value
    if "run" not in session_state:
        logger.debug("No 'run' in session state to clean up")
        return
    try:
        logger.debug("Exiting simulation...")
        session_state["run"].exit(reason="session deleted")
    except Exception:
        logger.exception("Failed to cleanly exit simulation on delete")
    finally:
        logger.debug("Session cleanup complete.")


def spacer(h: int = 24) -> None:
    """Create a vertical spacer of given height."""
    gr.HTML(f"<div style='height:{h}px'></div>")


def wpm_to_cps(wpm: int) -> float:
    """Convert words-per-minute to characters-per-second.

    Assumes average word length of 5 characters.
    """
    return max(1.0, (wpm * 5) / 60.0)


def slow_yield_chars(
    message: str,
    wpm: int = 180,  # ~15 cps
    min_yield_interval: float = 0.03,  # don’t spam UI; yield at most ~33 FPS
) -> Iterator[str]:
    """Yield a message one character at a time, simulating human typing speed."""
    cps = wpm_to_cps(wpm)
    per_char = 1.0 / cps

    # Natural micro-pauses after punctuation
    pauses = {
        ".": 0.35,
        "!": 0.35,
        "?": 0.35,
        ",": 0.12,
        ";": 0.15,
        ":": 0.15,
        "\n": 0.22,
        "—": 0.10,
        "…": 0.20,
    }

    built = []
    next_yield_at = time.perf_counter()  # throttle UI updates

    for ch in message:
        built.append(ch)
        time.sleep(per_char)

        # add extra pause after certain punctuation
        if ch in pauses:
            time.sleep(pauses[ch])

        now = time.perf_counter()
        if now >= next_yield_at:
            yield "".join(built)
            next_yield_at = now + min_yield_interval

    # final flush
    yield "".join(built)


def stream_msg(message: str) -> Iterator[str]:
    """Streams a message at about reading speed."""
    for partial in slow_yield_chars(
        message,
        # wpm=random.randint(150, 220),
    ):
        yield partial


def create_run(state: SessionState, token_value: Optional[str] = None) -> RunManager:
    """Create a new RunManager and return it."""
    if "game_config" not in state:
        logger.error("App state missing game_config in create_run.")
        raise gr.Error(USER_FRIENDLY_EXC)
    if "player_id" not in state:
        state["player_id"] = None
    if "pc_choice" not in state:
        state["pc_choice"] = None
    if "npc_choice" not in state:
        state["npc_choice"] = None
    try:
        run = RunManager.create(
            game=state["game_config"].name,
            source="widget",
            pc_choice=state["pc_choice"],
            npc_choice=state["npc_choice"],
            player_id=state["player_id"],
        )
    except Exception as e:
        logger.error(f"Error creating RunManager in create_run: {e}", exc_info=True)
        raise gr.Error(USER_FRIENDLY_EXC)
    return run


def format(msg_dict: Dict[str, Any]) -> str:
    """Format dict style message into a markdown formatted string for gradio display."""
    if not isinstance(msg_dict, dict):
        logger.error(
            f"Received non-dict message in format: {msg_dict}. Returning str()."
        )
        raise gr.Error(USER_FRIENDLY_EXC)
    if "type" not in msg_dict or "content" not in msg_dict:
        logger.warning(
            f"Received malformed message in format: {msg_dict}."
            " Dict must include 'type' and 'content' keys."
        )
        raise gr.Error(USER_FRIENDLY_EXC)
    t = (msg_dict.get("type") or "info").lower()
    c = msg_dict.get("content") or ""
    if not c:
        logger.warning("Received empty content in format.")
    if t == "warning":
        return f"#### Warning Message\n<em>{c}</em>"
    elif t == "error":
        return f"#### Error Message\n<em>{c}</em>"
    elif t == "info":
        return f"{c}"
    elif t == "system" or t == "assistant" or t == "ai":
        return c
    else:
        logger.warning(f"Unknown message type '{t}' in format; returning raw content.")
        return c


COMPONENTS = {
    "text": lambda q: gr.Textbox(
        label=q.get("label", ""),
        placeholder=q.get("placeholder", ""),
        lines=1,
        show_label=bool(q.get("label")),
        info=q.get("info", ""),
    ),
    "textarea": lambda q: gr.Textbox(
        label=q.get("label", ""),
        placeholder=q.get("placeholder", ""),
        lines=4,
        show_label=bool(q.get("label")),
        info=q.get("info", ""),
    ),
    "bool": lambda q: gr.Checkbox(label=q.get("label", "")),
    "email": lambda q: gr.Textbox(
        label=q.get("label", ""),
        placeholder=q.get("placeholder") or "name@example.com",
        lines=1,
        show_label=bool(q.get("label")),
        info=q.get("info", ""),
    ),
    "phone": lambda q: gr.Textbox(
        label=q.get("label", ""),
        placeholder=q.get("placeholder") or "+1 555 123 4567",
        lines=1,
        show_label=bool(q.get("label")),
        info=q.get("info", ""),
    ),
    "number": lambda q: gr.Number(label=q.get("label", ""), info=q.get("info", "")),
    "select": lambda q: gr.Dropdown(
        label=q.get("label", ""),
        choices=q.get("options", []),
        multiselect=False,
        info=q.get("info", ""),
    ),
    "multiselect": lambda q: gr.Dropdown(
        label=q.get("label", ""),
        choices=q.get("options", []),
        multiselect=True,
        info=q.get("info", ""),
    ),
    "radio": lambda q: gr.Radio(
        label=q.get("label", ""), choices=q.get("options", []), info=q.get("info", "")
    ),
    "checkboxes": lambda q: gr.CheckboxGroup(
        label=q.get("label", ""),
        show_label=bool(q.get("label")),
        choices=q.get("options", []),
        info=q.get("info", ""),
    ),
}


def make_component(question: Dict[str, Any]) -> gr.Component:
    """Create a Gradio component for a consent question spec."""
    t = (question.get("type") or "text").lower()
    factory = COMPONENTS.get(t, COMPONENTS["text"])
    return factory(question)  # type: ignore


def validate_email(val: str) -> bool:
    """Check if the email is valid."""
    if not val:
        return True  # handled by required
    return "@" in val and "." in val.split("@")[-1]


def validate_phone(val: str) -> bool:
    """Check if the phone number is valid (at least 10 digits)."""
    if not val:
        return True
    digits = [c for c in val if c.isdigit()]
    return len(digits) >= 10


def collect_form_answers(
    spec: Dict[str, Any], values: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """Collect and validate consent form answers.

    Returns (ok, message, answers_dict). If not ok, message is an error string.
    Expected order of *values matches build_consent(...).fields ordering.
    """
    logger.debug(f"collect_form_answers called with values: {values}")
    questions: List[Dict[str, Any]] = spec.get("questions", [])
    answers = {}
    errors = []

    for q, v in zip(questions, values):
        logger.debug(f"Processing question {q} with value '{v}'")
        qid = q.get("key", "")
        required = bool(q.get("required", False))
        atype = (q.get("type") or "text").lower()

        label = q.get("label")
        human_readable_label = label or qid.replace("_", " ").capitalize()

        if required and (v is None or v == "" or (isinstance(v, list) and not v)):
            errors.append(f"- {human_readable_label} is required.")
        if atype == "email" and not validate_email(v):
            errors.append(f"- {human_readable_label}" " must be a valid email.")
        if atype == "phone" and not validate_phone(v):
            errors.append(
                f"- {human_readable_label}" " must be a valid 10+ digit phone number."
            )
        answers[qid] = v

    if errors:
        return False, "<br>".join(errors), {}

    return True, "✅ Thanks! Consent recorded.", answers
