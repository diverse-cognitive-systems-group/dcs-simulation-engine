"""Validation, results, and persistence for a character evaluation."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

RESPONSE_TYPES = ("ai", "info", "error", "warning")
FEEDBACK_FLAGS = ("doesnt_make_sense", "out_of_character", "other")


@dataclass
class Turn:
    """A PC message or opening, followed by the events from that step."""

    prompt: dict | None = None
    output: list[dict] = field(default_factory=list)
    recorded: list[dict] | None = None


def transcript_parts(transcript, *, opening):
    """Group consecutive events into turns and leave branches in place."""
    parts = []
    turn = Turn() if opening else None
    for entry in transcript:
        if entry["type"] == "branch" or entry["source"] == "pc":
            if turn is not None:
                parts.append(turn)
            if entry["type"] == "branch":
                parts.append(entry)
                turn = None
            else:
                turn = Turn(prompt=entry)
        else:
            if turn is None:
                raise ValueError("A branch must continue from its fork with a PC message or another branch.")
            turn.output.append(entry)
    if turn is not None:
        parts.append(turn)
    return parts


def is_response(entry):
    """Identify a simulator response that an evaluator can rate."""
    return entry.get("source") == "npc"


def iter_sessions(session, *, opening=True):
    """Yield a session and its descendants with their opening-turn policy."""
    yield session, opening
    for entry in session["transcript"]:
        if entry["type"] == "branch":
            yield from iter_sessions(entry, opening=False)


def _text(value, label, *, allow_blank=False):
    if not isinstance(value, str) or (not allow_blank and not value.strip()):
        raise ValueError(f"{label} must be {'a string' if allow_blank else 'a nonblank string'}.")


def _validate_transcript(session, label, session_ids, *, opening):
    session_id = session.get("session_id")
    if session_id is not None:
        _text(session_id, f"{label}.session_id")
        if session_id in session_ids:
            raise ValueError(f"{label}.session_id already appears elsewhere in the evaluation.")
        session_ids.add(session_id)
    _text(session.get("description", ""), f"{label}.description", allow_blank=True)
    transcript = session.get("transcript")
    if not isinstance(transcript, list):
        raise ValueError(f"{label}.transcript must be a list.")

    for index, entry in enumerate(transcript, 1):
        name = f"{label}, transcript entry {index}"
        if not isinstance(entry, dict):
            raise ValueError(f"{name} must be an object.")
        kind, source = entry.get("type"), entry.get("source")
        if kind == "branch":
            _validate_transcript(entry, f"{name} (branch)", session_ids, opening=False)
            continue
        if kind not in ("message", "info", "error", "warning") or source not in ("pc", "npc", "system"):
            raise ValueError(f"{name} has an invalid type or source.")
        if source == "pc" and kind != "message":
            raise ValueError(f"{name}: PC inputs must be messages.")
        _text(entry.get("content"), f"{name}.content", allow_blank=source != "pc")
        if "evaluator_note" in entry:
            _text(entry["evaluator_note"], f"{name}.evaluator_note", allow_blank=True)
        feedback = entry.get("evaluator_feedback")
        if feedback is not None:
            if not is_response(entry) or not isinstance(feedback, dict):
                raise ValueError(f"{name}: feedback must be an object on a simulator response.")
            for key in ("liked", *FEEDBACK_FLAGS):
                if not isinstance(feedback.get(key), bool):
                    raise ValueError(f"{name}.evaluator_feedback.{key} must be a boolean.")
            _text(feedback.get("comment", ""), f"{name}.evaluator_feedback.comment", allow_blank=True)
    try:
        transcript_parts(transcript, opening=opening)
    except ValueError as exc:
        raise ValueError(f"{label}: {exc}") from exc


def load_evaluation_file(path: Path) -> dict:
    """Read and validate the evaluation and every nested transcript."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("The evaluation must be a JSON object.")
    _text(data.get("character_hid"), "character_hid")
    if data.get("evaluator_id") is None:
        data["evaluator_id"] = ""
    _text(data["evaluator_id"], "evaluator_id", allow_blank=True)
    for key in ("created_at", "updated_at"):
        _text(data.get(key), key)
        datetime.fromisoformat(data[key])
    results = data.get("results")
    if results is not None and not isinstance(results, dict):
        raise ValueError("results must be an object or null.")
    sessions = data.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list.")
    session_ids = set()
    for index, session in enumerate(sessions, 1):
        label = f"Session {index}"
        if not isinstance(session, dict):
            raise ValueError(f"{label} must be an object.")
        for key in ("game", "npc_hid", "pc_hid"):
            _text(session.get(key), f"{label}.{key}")
        _validate_transcript(session, label, session_ids, opening=True)
    return data


def select_sessions(data, *, only=None, exclude=None):
    """Resolve one-based top-level session selectors to indices."""
    total = len(data["sessions"])
    for number in list(only or []) + list(exclude or []):
        if not 1 <= number <= total:
            raise ValueError(f"Session {number} is out of range. The file has {total} session(s).")
    return [index for index in range(total) if (not only or index + 1 in only) and (not exclude or index + 1 not in exclude)]


def _transcript_counts(sessions):
    turns = 0
    pending = 0
    responses = []
    for root in sessions:
        for session, opening in iter_sessions(root):
            parts = transcript_parts(session["transcript"], opening=opening)
            pending += not parts
            for part in parts:
                if isinstance(part, Turn):
                    output = [entry for entry in part.output if is_response(entry)]
                    responses.extend(output)
                    turns += part.prompt is not None
                    pending += not output
    return turns, pending, responses


def _completion_issues(pending, response_count, rated_count, summary):
    issues = []
    if pending:
        issues.append(f"{pending} opening(s), turn(s), or branches missing a simulator response")
    elif not response_count:
        issues.append("No simulator responses")
    if unrated := response_count - rated_count:
        issues.append(f"{unrated} simulator response(s) missing evaluator feedback")
    if not isinstance(summary, str) or not summary.strip():
        issues.append("Missing evaluator summary in results.summary")
    return issues


def evaluation_completion_issues(data):
    """Describe work still needed before publishing an evaluation."""
    _, pending, responses = _transcript_counts(data["sessions"])
    rated_count = sum(response.get("evaluator_feedback") is not None for response in responses)
    summary = (data.get("results") or {}).get("summary")
    issues = _completion_issues(pending, len(responses), rated_count, summary)
    if not data["evaluator_id"].strip():
        issues.insert(0, "Missing evaluator_id. Set it in the evaluation file")
    return issues


def compute_results(data: dict) -> dict:
    """Summarize all turns, responses, and ratings while preserving written results."""
    turns, pending, responses = _transcript_counts(data["sessions"])
    ratings = [entry["evaluator_feedback"] for entry in responses if entry.get("evaluator_feedback") is not None]
    results = dict(data.get("results") or {})
    summary = results.setdefault("summary", "")
    results.update(
        complete=not _completion_issues(pending, len(responses), len(ratings), summary),
        counts={
            "sessions": len(data["sessions"]),
            "turns": turns,
            "rated": len(ratings),
            "thumbs_up": sum(rating["liked"] for rating in ratings),
            "thumbs_down": sum(not rating["liked"] for rating in ratings),
            **{flag: sum(rating[flag] for rating in ratings) for flag in FEEDBACK_FLAGS},
        },
        response_types={
            kind: sum(entry["type"] == ("message" if kind == "ai" else kind) for entry in responses) for kind in RESPONSE_TYPES
        },
    )
    return results


def save_evaluation_file(path: Path, data: dict) -> None:
    """Save progress and freshly computed results together, if anything changed."""
    data["results"] = compute_results(data)
    if json.loads(path.read_text(encoding="utf-8")) == data:
        return
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(data, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def backup_evaluation_file(path: Path) -> Path:
    """Keep an exclusive, durable copy of the whole file before destructive replay."""
    contents = path.read_bytes()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    with NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f"{path.stem}.backup-{timestamp}-",
        suffix=".json",
        delete=False,
    ) as output:
        backup = Path(output.name)
        try:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
    return backup


def render_evaluation_summary(data, selected):
    """Show pending work for the selection and completion for the whole file."""
    turns, pending, responses = _transcript_counts([data["sessions"][index] for index in selected])
    unrated = sum(entry.get("evaluator_feedback") is None for entry in responses)
    complete = "yes" if compute_results(data)["complete"] else "no"
    return "\n".join(
        [
            "[bold]Evaluation File Summary[/bold]",
            f"  {len(selected)} top-level session(s), {turns} PC turn(s)",
            f"  {pending} opening(s), turn(s), or branches awaiting a simulator response",
            f"  {unrated} simulator response(s) awaiting feedback",
            f"  Evaluation summary complete: {complete}",
        ]
    )
