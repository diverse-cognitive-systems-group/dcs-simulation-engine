"""Export a completed scenarios file to a results directory.

The output directory has the same structure that ``dcs-utils generate report``
expects: sessions.json, session_events.json, characters.json, players.json,
assignments.json, experiments.json, and __manifest__.json.

Each Scenario becomes one session; each Attempt within a scenario becomes two
session events (inbound player message + outbound NPC response with feedback).
The EvaluatorFeedback fields map 1-to-1 onto the session_events feedback
object so the existing analysis pipeline can process them without any changes.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dcs_utils.hitl import EvaluatorFeedback, ScenarioFile
from dcs_utils.hitl.generate import load_scenario_file

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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_results(
    scenarios_path: Path,
    *,
    evaluator_id: str = "evaluator",
    output_dir: Path | None = None,
) -> Path:
    """Convert a completed scenarios file to a results directory.

    The results directory is placed next to the scenarios file by default
    (``<hid>-scenario-results/``), or at ``output_dir`` if specified.

    Args:
        scenarios_path: Path to the ``<hid>-scenarios.json`` file.
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

    for group in scenario_file.scenario_groups:
        for scenario in group.scenarios:
            session_id = str(uuid.uuid4())
            started_at = generated_at
            turns_completed = sum(
                1 for a in scenario.attempts if a.simulator_response is not None
            )

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
                        "expected_pc_behavior": scenario.expected_pc_behavior,
                    },
                    "last_seq": turns_completed * 2,
                    "created_at": started_at,
                    "updated_at": _now_iso(),
                }
            )

            seq = 0
            for turn_index, attempt in enumerate(scenario.attempts):
                if attempt.simulator_response is None:
                    continue  # skip attempts without a response

                ts = attempt.evaluator_feedback.submitted_at if attempt.evaluator_feedback else _now_iso()

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

                # Outbound NPC response (with feedback)
                seq += 1
                session_events.append(
                    {
                        "session_id": session_id,
                        "seq": seq,
                        "event_id": str(uuid.uuid4()),
                        "event_ts": ts,
                        "direction": "outbound",
                        "event_type": "message",
                        "event_source": "npc",
                        "content": attempt.simulator_response,
                        "content_format": "markdown",
                        "turn_index": turn_index,
                        "visible_to_user": True,
                        "feedback": _feedback_to_event_feedback(attempt.evaluator_feedback),
                    }
                )

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

    # experiments.json
    experiments = [
        {
            "experiment_id": str(uuid.uuid4()),
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
        "total_scenarios": sum(len(g.scenarios) for g in scenario_file.scenario_groups),
        "total_attempts": sum(
            len(s.attempts)
            for g in scenario_file.scenario_groups
            for s in g.scenarios
        ),
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
    _write("experiments.json", experiments)
    _write("assignments.json", [])

    return output_dir
