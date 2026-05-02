"""Export a completed test cases file to a results directory.

The output directory has the same structure that ``dcs generate report``
expects: sessions.json, session_events.json, characters.json, players.json,
assignments.json, runs.json, and __manifest__.json.

Each Scenario becomes one session; each Attempt within a scenario becomes an
inbound player message plus one or more outbound simulator/system events.
The EvaluatorFeedback fields map 1-to-1 onto the session_events feedback
object so the existing analysis pipeline can process them without any changes.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dcs_simulation_engine.hitl import Attempt, EvaluatorFeedback, ScenarioFile
from dcs_simulation_engine.hitl.generate import load_scenario_file

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEV_CHARS_PATH = _REPO_ROOT / "database_seeds" / "dev" / "characters.json"
_PROD_CHARS_PATH = _REPO_ROOT / "database_seeds" / "prod" / "characters.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _feedback_to_event_feedback(fb: EvaluatorFeedback | None) -> dict | None:
    if fb is None:
        return None
    return {
        "liked": fb.liked,
        "comment": fb.comment or None,
        "doesnt_make_sense": fb.doesnt_make_sense,
        "out_of_character": fb.out_of_character,
        "other": fb.other,
        "submitted_at": fb.submitted_at,
    }


def _attempt_response_events(attempt) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    if attempt.simulator_response is not None:
        events.append((str(attempt.simulator_response_type or "ai"), attempt.simulator_response))

    for event in attempt.simulator_extra_events:
        events.append(
            (
                str(event.get("event_type") or "info"),
                str(event.get("content") or ""),
            )
        )
    return events


def _is_completed_attempt(attempt: Attempt) -> bool:
    return attempt.simulator_response is not None and attempt.evaluator_feedback is not None


def _export_event_shape(event_type: str) -> tuple[str, str, str]:
    lowered = event_type.lower()
    if lowered == "ai":
        return "message", "npc", "markdown"
    if lowered not in {"info", "error", "warning"}:
        lowered = "info"
    return lowered, "system", "plain_text"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_results(
    scenarios_path: Path,
    *,
    evaluator_id: str = "evaluator",
    output_dir: Path | None = None,
) -> Path:
    """Convert a completed test cases file to a results directory.

    The results directory is placed next to the test cases file by default
    (``<hid>-scenario-results/``), or at ``output_dir`` if specified.

    Args:
        scenarios_path: Path to the ``<hid>-test-cases.json`` file.
        evaluator_id: Name/ID recorded as the synthetic player.
        output_dir: Override the output directory path.

    Returns:
        The path to the created results directory.
    """
    scenario_file: ScenarioFile = load_scenario_file(scenarios_path)
    npc_hid = scenario_file.npc_hid

    if output_dir is None:
        output_dir = scenarios_path.parent / f"{npc_hid}-scenario-results"
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = scenario_file.generated_at
    player_id = f"evaluator-{evaluator_id}"

    sessions: list[dict] = []
    session_events: list[dict] = []
    total_source_scenarios = 0
    total_source_attempts = 0
    exported_scenarios = 0
    exported_attempts = 0

    for group in scenario_file.scenario_groups:
        for scenario in group.scenarios:
            total_source_scenarios += 1
            total_source_attempts += len(scenario.attempts)
            completed_attempts = [
                (turn_index, attempt) for turn_index, attempt in enumerate(scenario.attempts) if _is_completed_attempt(attempt)
            ]
            if not completed_attempts:
                continue

            session_id = str(uuid.uuid4())
            started_at = generated_at
            turns_completed = len(completed_attempts)
            exported_scenarios += 1
            exported_attempts += turns_completed

            sessions.append(
                {
                    "session_id": session_id,
                    "name": f"hitl-{npc_hid}-{scenario.id}",
                    "player_id": player_id,
                    "game_name": scenario.game,
                    "source": "hitl",
                    "pc_hid": scenario.pc_hid,
                    "npc_hid": npc_hid,
                    "session_started_at": started_at,
                    "session_ended_at": _now_iso(),
                    "termination_reason": "hitl_complete",
                    "status": "closed",
                    "turns_completed": turns_completed,
                    "model_profile": {
                        "updater_model": None,
                        "validator_model": None,
                        "scorer_model": None,
                    },
                    "game_config_snapshot": {
                        "pressure_category": group.pressure_category,
                        "expected_failure_mode": group.expected_failure_mode,
                    },
                    "last_seq": 0,
                    "created_at": started_at,
                    "updated_at": _now_iso(),
                }
            )

            seq = 0
            for turn_index, attempt in completed_attempts:
                ts = attempt.evaluator_feedback.submitted_at

                # Inbound player message
                seq += 1
                session_events.append(
                    {
                        "session_id": session_id,
                        "seq": seq,
                        "event_id": str(uuid.uuid4()),
                        "event_ts": ts,
                        "direction": "inbound",
                        "event_type": "message",
                        "event_source": "user",
                        "content": attempt.player_message,
                        "content_format": "plain_text",
                        "turn_index": turn_index,
                        "visible_to_user": True,
                    }
                )

                # Outbound simulator/system response(s)
                response_events = _attempt_response_events(attempt)
                for response_idx, (response_type, content) in enumerate(response_events):
                    event_type, event_source, content_format = _export_event_shape(response_type)
                    seq += 1
                    event_doc = {
                        "session_id": session_id,
                        "seq": seq,
                        "event_id": str(uuid.uuid4()),
                        "event_ts": ts,
                        "direction": "outbound",
                        "event_type": event_type,
                        "event_source": event_source,
                        "content": content,
                        "content_format": content_format,
                        "turn_index": turn_index,
                        "visible_to_user": True,
                    }
                    if response_idx == 0:
                        event_doc["feedback"] = _feedback_to_event_feedback(attempt.evaluator_feedback)
                    session_events.append(event_doc)

            sessions[-1]["last_seq"] = seq

    # characters.json — include the NPC character document
    char_doc = _load_character_doc(npc_hid)
    characters = [char_doc] if char_doc else []

    # players.json
    players = [
        {
            "player_id": player_id,
            "access_key": player_id,
            "source": "hitl",
            "created_at": generated_at,
        }
    ]

    # runs.json
    runs_metadata = [
        {
            "run_id": str(uuid.uuid4()),
            "name": f"{npc_hid} HITL Scenario Test",
            "run_config": {"source": "hitl", "npc_hid": npc_hid},
            "created_at": generated_at,
        }
    ]

    # __manifest__.json
    manifest = {
        "source": "scenario-testing",
        "npc_hid": npc_hid,
        "generated_at": generated_at,
        "scenarios_path": str(scenarios_path),
        "total_scenarios": exported_scenarios,
        "total_attempts": exported_attempts,
        "source_total_scenarios": total_source_scenarios,
        "source_total_attempts": total_source_attempts,
        "skipped_scenarios": total_source_scenarios - exported_scenarios,
        "skipped_attempts": total_source_attempts - exported_attempts,
    }

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
