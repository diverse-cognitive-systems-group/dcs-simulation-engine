"""Data models for the human-in-the-loop (HITL) scenario testing pipeline."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

SimulatorResponseType = Literal["ai", "info", "error", "warning"]


class EvaluatorFeedback(BaseModel):
    """Evaluator rating for one simulator response.

    Field names and semantics match the feedback object in session_events
    so the export pipeline can map these directly to report-compatible data.
    """

    liked: bool
    comment: str = ""
    doesnt_make_sense: bool = False
    out_of_character: bool = False
    other: bool = False
    submitted_at: str  # ISO-8601 timestamp


class Attempt(BaseModel):
    """A single player message, the simulator's response, and evaluator feedback."""

    player_message: str
    simulator_response: str | None = None
    simulator_response_type: SimulatorResponseType | None = None
    simulator_extra_events: list[dict[str, str]] = Field(default_factory=list)
    evaluator_feedback: EvaluatorFeedback | None = None


class Scenario(BaseModel):
    """One test scenario: a starting context and one or more player attempts."""

    id: str
    description: str
    game: str
    pc_hid: str
    parent_session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("parent_session_id", "context_session_id"),
    )
    conversation_history: list[dict] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)


class ScenarioGroup(BaseModel):
    """Scenarios grouped by the expected failure mode they probe."""

    group_id: str
    label: str
    expected_failure_mode: str
    pressure_category: str
    scenarios: list[Scenario] = Field(default_factory=list)


class ScenarioFile(BaseModel):
    """Top-level container for a character's scenario test suite."""

    npc_hid: str
    generated_at: str  # ISO-8601 timestamp
    scenario_groups: list[ScenarioGroup] = Field(default_factory=list)
