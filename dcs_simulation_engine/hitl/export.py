"""Export a HITL evaluation to a `dcs report results` bundle."""

import json
import uuid
from pathlib import Path

from dcs_simulation_engine.hitl.evaluation import evaluation_completion_issues, load_evaluation_file

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEV_CHARS_PATH = _REPO_ROOT / "database_seeds" / "dev" / "characters.json"
_PROD_CHARS_PATH = _REPO_ROOT / "database_seeds" / "prod" / "characters.json"


def _load_character_doc(npc_hid: str) -> dict | None:
    """Try to find the character document in dev then prod seeds."""
    for path in (_DEV_CHARS_PATH, _PROD_CHARS_PATH):
        if not path.exists():
            continue
        chars = json.loads(path.read_text(encoding="utf-8"))
        for char in chars:
            if char.get("hid") == npc_hid:
                return char
    return None


def _feedback_to_event_feedback(feedback: dict, updated_at: str) -> dict:
    return {
        "liked": feedback["liked"],
        "comment": feedback.get("comment") or None,
        "doesnt_make_sense": feedback["doesnt_make_sense"],
        "out_of_character": feedback["out_of_character"],
        "other": feedback["other"],
        "submitted_at": feedback.get("submitted_at") or updated_at,
    }


def export_results(
    evaluation_path: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Convert an evaluation into the standard results files before reporting."""
    evaluation = load_evaluation_file(evaluation_path)
    character_hid = evaluation["character_hid"]
    completion_issues = evaluation_completion_issues(evaluation)
    summary = (evaluation.get("results") or {}).get("summary")

    if output_dir is None:
        output_dir = evaluation_path.parent / f"{character_hid}-scenario-results"

    created_at = evaluation["created_at"]
    updated_at = evaluation["updated_at"]
    evaluator_id = evaluation["evaluator_id"].strip()
    player_id = evaluator_id or None

    sessions: list[dict] = []
    session_events: list[dict] = []

    def append_session(session, root, *, parent_id=None, parent_seq=None):
        session_id = session.get("session_id") or str(uuid.uuid4())
        session_doc = {
            "session_id": session_id,
            "name": f"hitl-{root['npc_hid']}-{session_id}",
            "player_id": player_id,
            "game_name": root["game"],
            "source": "hitl",
            "pc_hid": root["pc_hid"],
            "npc_hid": root["npc_hid"],
            "evaluator_description": session.get("description", ""),
            "session_started_at": created_at,
            "session_ended_at": updated_at,
            "termination_reason": "hitl_complete",
            "status": "closed",
            "model_profile": {
                "updater_model": None,
                "validator_model": None,
                "scorer_model": None,
            },
            "game_config_snapshot": {},
            "created_at": created_at,
            "updated_at": updated_at,
        }
        if parent_id is not None:
            session_doc["branch_from_session_id"] = parent_id
            session_doc["branch_from_seq"] = parent_seq
        sessions.append(session_doc)

        seq = turn_index = 0
        branches = []
        for entry in session["transcript"]:
            if entry["type"] == "branch":
                branches.append((entry, seq))
                continue
            source = entry["source"]
            is_pc = source == "pc"
            turn_index += is_pc
            seq += 1
            event_doc = {
                "session_id": session_id,
                "seq": seq,
                "event_id": str(uuid.uuid4()),
                "event_ts": entry.get("event_ts") or updated_at,
                "direction": "inbound" if is_pc else "outbound",
                "event_type": entry["type"],
                "event_source": "user" if is_pc else source,
                "content": entry["content"],
                "content_format": "markdown" if source == "npc" else "plain_text",
                "turn_index": turn_index,
                "visible_to_user": True,
            }
            if "evaluator_note" in entry:
                event_doc["evaluator_note"] = entry["evaluator_note"]
            if (feedback := entry.get("evaluator_feedback")) is not None:
                event_doc["feedback"] = _feedback_to_event_feedback(feedback, updated_at)
            session_events.append(event_doc)
        session_doc.update(last_seq=seq, turns_completed=turn_index)

        for branch, fork_seq in branches:
            append_session(branch, root, parent_id=session_id, parent_seq=fork_seq)

    for root in evaluation["sessions"]:
        append_session(root, root)

    # Keep the same report inputs, including local seed metadata when available.
    character_hids = sorted({character_hid} | {session["npc_hid"] for session in sessions})
    characters = [doc for hid in character_hids if (doc := _load_character_doc(hid)) is not None]

    players = []
    if sessions and player_id is not None:
        players.append({"player_id": player_id, "access_key": player_id, "source": "hitl", "created_at": created_at})
    runs_metadata = [
        {
            "run_id": str(uuid.uuid4()),
            "name": f"{character_hid} HITL Scenario Test",
            "run_config": {"source": "hitl", "npc_hid": character_hid},
            "created_at": created_at,
        }
    ]
    manifest = {
        "source": "scenario-testing",
        "npc_hid": character_hid,
        "evaluator_id": evaluator_id,
        "evaluation_summary": summary if isinstance(summary, str) else "",
        "generated_at": created_at,
        "evaluation_path": str(evaluation_path),
        "total_sessions": len(sessions),
        "total_turns": sum(session["turns_completed"] for session in sessions),
        "evaluation_status": {"complete": not completion_issues, "issues": completion_issues},
    }

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write all files
    def _write(name: str, data) -> None:
        (output_dir / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    _write("__manifest__.json", manifest)
    _write("sessions.json", sessions)
    _write("session_events.json", session_events)
    _write("characters.json", characters)
    _write("players.json", players)
    _write("runs.json", runs_metadata)
    _write("assignments.json", [])

    return output_dir
