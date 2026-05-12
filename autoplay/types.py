"""Types shared by autoplay."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlayerTurn:
    """One visible exchange from the API player's point of view."""

    role: str
    content: str
    event_type: str = "message"
    failure_type: str | None = None


@dataclass(frozen=True)
class PlayerContext:
    """Visible gameplay context passed to an API player."""

    run_name: str
    player_id: str
    model_id: str
    assignment: dict[str, Any]
    session_id: str
    session_meta: dict[str, Any]
    turns: int
    history: tuple[PlayerTurn, ...]
    last_error: str | None = None


@dataclass
class AssignmentResult:
    """Result for one assignment attempted by the harness."""

    assignment_id: str
    game_name: str
    session_id: str
    status: str
    turns: int = 0
    error: str | None = None


@dataclass
class HarnessResult:
    """Aggregate result for one autoplay run."""

    model_id: str
    player_id: str
    api_key: str
    run_name: str
    assignments: list[AssignmentResult] = field(default_factory=list)

    @property
    def completed_assignments(self) -> int:
        """Return the number of assignments completed by the backend."""
        return sum(1 for assignment in self.assignments if assignment.status == "completed")
