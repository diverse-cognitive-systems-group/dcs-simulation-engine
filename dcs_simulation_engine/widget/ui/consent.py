"""Consent form UI components."""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Tuple

import gradio as gr


class ConsentUI(NamedTuple):
    """Holds references to consent form UI components."""

    form_group: gr.Group
    fields: Dict[str, gr.Component]
    submit_btn: gr.Button
    back_btn: gr.Button
    token_group: gr.Group
    token_text: gr.Textbox
    token_continue_btn: gr.Button


# --- helpers ---------------------------------------------------------------


def _spacer(h: int = 16) -> None:
    """Insert vertical space of height h pixels."""
    gr.HTML(f"<div style='height:{h}px'></div>")


# Map your config answer_type -> Gradio component factory
_COMPONENTS = {
    "text": lambda q: gr.Textbox(
        label=q.get("prompt", ""),
        placeholder=q.get("placeholder", ""),
        lines=1,
        show_label=True,
    ),
    "textarea": lambda q: gr.Textbox(
        label=q.get("prompt", ""),
        placeholder=q.get("placeholder", ""),
        lines=4,
        show_label=True,
    ),
    "bool": lambda q: gr.Checkbox(label=q.get("prompt", "")),
    "email": lambda q: gr.Textbox(
        label=q.get("prompt", ""),
        placeholder="name@example.com",
        lines=1,
        show_label=True,
    ),
    "phone": lambda q: gr.Textbox(
        label=q.get("prompt", ""),
        placeholder="+1 555 123 4567",
        lines=1,
        show_label=True,
    ),
    "number": lambda q: gr.Number(label=q.get("prompt", "")),
    "select": lambda q: gr.Dropdown(
        label=q.get("prompt", ""), choices=q.get("options", []), multiselect=False
    ),
    "multiselect": lambda q: gr.Dropdown(
        label=q.get("prompt", ""), choices=q.get("options", []), multiselect=True
    ),
    "radio": lambda q: gr.Radio(
        label=q.get("prompt", ""), choices=q.get("options", [])
    ),
    "checkboxes": lambda q: gr.CheckboxGroup(
        label=q.get("prompt", ""), choices=q.get("options", [])
    ),
}


def _make_component(question: Dict[str, Any]) -> gr.components.Component:
    t = (question.get("answer_type") or "text").lower()
    factory = _COMPONENTS.get(t, _COMPONENTS["text"])
    return factory(question)


def _required_ok(val: Any) -> bool:
    """Check if a required field value is non-empty."""
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() != ""
    if isinstance(val, (list, tuple, set)):
        return len(val) > 0
    return True


def _validate_email(val: str) -> bool:
    """Check if the email is valid."""
    if not val:
        return True  # handled by required
    return "@" in val and "." in val.split("@")[-1]


def _validate_phone(val: str) -> bool:
    """Check if the phone number is valid (at least 10 digits)."""
    if not val:
        return True
    digits = [c for c in val if c.isdigit()]
    return len(digits) >= 10


def collect_consent_answers(
    consent_spec: Dict[str, Any], *values: Any
) -> Tuple[bool, str, Dict[str, Any]]:
    """Collect and validate consent form answers.

    Returns (ok, message, answers_dict). If not ok, message is an error string.
    Expected order of *values matches build_consent(...).fields ordering.
    """
    questions: List[Dict[str, Any]] = consent_spec.get("questions", [])
    answers = {}
    errors = []

    for q, v in zip(questions, values):
        qid = (
            q.get("id")
            or q.get("name")
            or q.get("prompt", "q").lower().replace(" ", "_")
        )
        required = bool(q.get("required", False))
        atype = (q.get("answer_type") or "text").lower()

        if required and not _required_ok(v):
            errors.append(f"❌ {q.get('prompt', qid)} is required.")
        if atype == "email" and not _validate_email(v):
            errors.append(f"❌ {q.get('prompt', qid)} must be a valid email.")
        if atype == "phone" and not _validate_phone(v):
            errors.append(f"❌ {q.get('prompt', qid)} must be a valid phone number.")

        answers[qid] = v

    if errors:
        return False, "\n".join(errors), {}

    return True, "✅ Thanks! Consent recorded.", answers


# --- builder ---------------------------------------------------------------


def build_consent(consent_config: Dict[str, Any]) -> ConsentUI:
    """Builds consent form UI components.

    Builds two exclusive views:
      1) Consent form (hidden by default)
      2) One-time token display (hidden by default)

    consent_config is expected to look like:
    {
      "preamble": "## Welcome ...",
      "questions": [
         {"id":"age","prompt":"Your age","answer_type":"number","required":True},
         {"id":"email","prompt":"Email","answer_type":"email","required":False},
         {"id":"agree","prompt":"I consent","answer_type":"bool","required":True},
         ...
      ]
    }
    """
    with gr.Group(visible=False) as form_group:
        # Preamble
        pre_md = consent_config.get("preamble") or "**Consent**"
        gr.Markdown(pre_md)
        _spacer(8)

        # Dynamic questions
        fields: Dict[str, gr.Component] = {}
        for q in consent_config.get("questions", []):
            comp = _make_component(q)
            fields[q.get("id") or q.get("name") or q.get("prompt", "q")] = comp

        _spacer(8)
        with gr.Row():
            back_btn = gr.Button("Back", variant="secondary")
            submit_btn = gr.Button("I Agree & Continue", variant="primary")

    with gr.Group(visible=False) as token_group:
        gr.Markdown("### Your One-Time Access Token")
        gr.Markdown(
            "> Save this **now**. You won’t be able to see it again here after you continue."
        )
        token_text = gr.Textbox(
            label="Token",
            interactive=False,
            lines=1,
            show_label=True,
        )
        _spacer(8)
        with gr.Row():
            token_continue_btn = gr.Button("I have saved my token", variant="primary")

    return ConsentUI(
        form_group=form_group,
        fields=fields,
        submit_btn=submit_btn,
        back_btn=back_btn,
        token_group=token_group,
        token_text=token_text,
        token_continue_btn=token_continue_btn,
    )
