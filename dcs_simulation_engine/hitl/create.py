"""Scaffold a character evaluation and read or write scenario files."""

import json
from datetime import datetime, timezone
from pathlib import Path

from dcs_simulation_engine.hitl import ScenarioFile

# Repo-relative paths
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS_DIR = _REPO_ROOT / "evaluations" / "characters"


def scenarios_path_for(hid: str) -> Path:
    """Return the expected output path for a character's evaluation cases file."""
    return _SCENARIOS_DIR / f"{hid}-evaluation-cases.json"


def evaluation_path_for(hid: str) -> Path:
    """Return the path for a character's evaluation scaffold."""
    filename = f"{hid}-evaluation.json"
    if not hid.strip() or "\\" in hid or "\0" in hid or Path(filename).name != filename:
        raise ValueError("Provide a character HID without path components.")
    return _SCENARIOS_DIR / filename


def build_scaffold(hid: str, game: str) -> dict:
    """Build evaluation guidance and one session with an empty transcript."""
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "character_hid": hid,
        "evaluator_id": "",
        "created_at": created_at,
        "updated_at": created_at,
        "description": (
            "This human-in-the-loop character evaluation assesses the model’s fidelity and elucidates the bounds "
            "of its modeling capabilities across contexts so it can be used appropriately."
        ),
        "evaluator_instructions": (
            "Thoroughly evaluate the character model instance across different interaction scenarios and conversation "
            "histories of varying lengths and types. If the character model is an ensemble that includes large language "
            "models (LLMs), test for common LLM failure modes such as hallucination and bias across those contexts. "
            "For example, check how well the model stays in character when presented with false information, ambiguous "
            "requests, demanding memory or reasoning tasks, or attempts to elicit behavior beyond the character’s abilities. "
            "Also check whether responses follow RPG-style interaction conventions, such as using 'yes, and' improvisation "
            "when the situation is ambiguous. Mark 'out of character' only when there is clear evidence that the response "
            "conflicts with the character’s established traits, abilities, knowledge, history, or other established details. "
            "Mark 'doesn’t make sense' when the response is too unclear or incoherent to understand or follow in context."
        ),
        "results": None,
        "sessions": [
            {
                "game": game,
                "npc_hid": hid,
                "pc_hid": "NA",
                "session_id": None,
                "description": "",
                "transcript": [],
            }
        ],
    }


def save_scaffold(scaffold: dict, path: Path) -> None:
    """Create an evaluation scaffold JSON file without overwriting an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(scaffold, indent=2, ensure_ascii=False)
    with path.open("x", encoding="utf-8") as file:
        file.write(contents)


def load_scenario_file(path: Path) -> ScenarioFile:
    """Load and parse a scenarios JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioFile.model_validate(data)


def save_scenario_file(path: Path, scenario_file: ScenarioFile) -> None:
    """Write a ScenarioFile back to disk (atomic via temp file)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(scenario_file.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
