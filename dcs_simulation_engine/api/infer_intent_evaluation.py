"""Helpers for generating or loading Infer Intent evaluations from persisted sessions."""

from typing import Any

from dcs_simulation_engine.api.models import (
    InferIntentEvaluation,
    InferIntentEvaluationResponse,
)
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    SessionEventRecord,
    SessionRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.ai_client import ScorerClient
from dcs_simulation_engine.utils.async_utils import maybe_await

INFER_INTENT_GAME_NAME = "Infer Intent"
LLM_EVAL_EVENT_TYPE = "llm_eval"


class InferIntentEvaluationUnavailableError(ValueError):
    """Raised when a requested Infer Intent evaluation cannot be produced."""


def extract_infer_intent_scoring_inputs(events: list[SessionEventRecord]) -> tuple[str, str]:
    """Rebuild the transcript and saved player intent prediction from persisted session events."""
    transcript_lines: list[str] = []
    found_prediction_command = False
    prediction = ""

    for event in sorted(events, key=lambda item: item.seq):
        if event.data.get(MongoColumns.VISIBLE_TO_USER) is False:
            continue

        if not found_prediction_command:
            if _is_prediction_command(event):
                found_prediction_command = True
                continue

            if event.direction == "inbound" and event.event_source == "user" and event.event_type == "message":
                transcript_lines.append(f"Player: {event.content}")
                continue

            if event.direction == "outbound" and event.event_source == "npc" and event.event_type == "message":
                transcript_lines.append(f"NPC: {event.content}")
                continue

            continue

        if event.direction == "inbound" and event.event_source == "user" and event.event_type == "message":
            prediction = event.content.strip()
            break

    if not found_prediction_command:
        raise InferIntentEvaluationUnavailableError("Infer Intent evaluation is unavailable because no prediction was saved.")
    if not prediction:
        raise InferIntentEvaluationUnavailableError(
            "Infer Intent evaluation is unavailable because the saved prediction could not be found."
        )

    return ("\n".join(transcript_lines), prediction)


async def generate_or_get_infer_intent_evaluation(
    *,
    provider: Any,
    session_id: str,
    player_id: str,
    condition: str | None = None,
) -> InferIntentEvaluationResponse | None:
    """Return a cached Infer Intent evaluation or generate and persist it once."""
    session = await maybe_await(provider.get_session(session_id=session_id, player_id=player_id))
    if session is None:
        return None

    _validate_infer_intent_session(session)

    events = await maybe_await(provider.list_session_events(session_id=session_id))
    cached_event = _find_cached_evaluation_event(events)
    if cached_event is not None:
        return InferIntentEvaluationResponse(
            session_id=session_id,
            event_id=cached_event.event_id,
            cached=True,
            evaluation=InferIntentEvaluation.model_validate_json(cached_event.content),
        )

    transcript, prediction = extract_infer_intent_scoring_inputs(events)
    npc = await _load_session_npc(provider=provider, session=session)
    scorer_result = await ScorerClient(npc=npc).score(transcript, prediction)
    evaluation = InferIntentEvaluation.model_validate(scorer_result.evaluation)

    append_event = getattr(provider, "append_session_event", None)
    if append_event is None:
        raise NotImplementedError("Infer Intent evaluation persistence is unavailable for this provider.")

    stored = await maybe_await(
        append_event(
            session_id=session_id,
            player_id=player_id,
            direction="internal",
            event_type=LLM_EVAL_EVENT_TYPE,
            event_source="system",
            content=scorer_result.raw_json,
            content_format="json",
            turn_index=int(session.data.get(MongoColumns.TURNS_COMPLETED, 0) or 0),
            visible_to_user=(condition == "learning"),
        )
    )
    if stored is None:
        return None

    return InferIntentEvaluationResponse(
        session_id=session_id,
        event_id=stored.event_id,
        cached=False,
        evaluation=evaluation,
    )


def _find_cached_evaluation_event(events: list[SessionEventRecord]) -> SessionEventRecord | None:
    for event in sorted(events, key=lambda item: item.seq):
        if event.direction == "internal" and event.event_source == "system" and event.event_type == LLM_EVAL_EVENT_TYPE:
            return event
    return None


def _is_prediction_command(event: SessionEventRecord) -> bool:
    return (
        event.direction == "inbound"
        and event.event_source == "user"
        and event.event_type == "command"
        and str(event.data.get(MongoColumns.COMMAND_NAME, "")).lower() == "predict-intent"
    )


def _validate_infer_intent_session(session: SessionRecord) -> None:
    if session.game_name != INFER_INTENT_GAME_NAME:
        raise InferIntentEvaluationUnavailableError("Infer Intent evaluation is only available for completed Infer Intent sessions.")

    termination_reason = str(session.data.get(MongoColumns.TERMINATION_REASON, "")).strip().lower()
    if termination_reason != "game_completed":
        raise InferIntentEvaluationUnavailableError("Infer Intent evaluation is not available until the game is completed.")


async def _load_session_npc(*, provider: Any, session: SessionRecord) -> CharacterRecord:
    npc_hid = str(session.data.get(MongoColumns.NPC_HID, "")).strip()
    if not npc_hid:
        raise InferIntentEvaluationUnavailableError("Infer Intent evaluation is unavailable because the session does not have a saved NPC.")
    return await maybe_await(provider.get_character(hid=npc_hid))
