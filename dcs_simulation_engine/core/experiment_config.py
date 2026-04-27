"""Experiment-level configuration models for assignment-driven studies."""

import re
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from dcs_simulation_engine.core.forms import (
    ExperimentForm,
)
from dcs_simulation_engine.utils.serde import SerdeMixin
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _normalize_game_ref(value: str) -> str:
    """Normalize a game reference so snake_case and Title Case can match."""
    return re.sub(r"[\s_-]+", "", value.strip().lower())


def _available_game_names() -> dict[str, str]:
    """Return normalized game-name aliases mapped to canonical display names."""
    games_dir = Path(__file__).resolve().parents[2] / "games"
    aliases: dict[str, str] = {}
    for path in games_dir.glob("*.y*ml"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                doc = yaml.safe_load(handle) or {}
        except Exception:
            continue
        raw_name = doc.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        canonical = raw_name.strip()
        aliases[_normalize_game_ref(canonical)] = canonical
        aliases[_normalize_game_ref(path.stem)] = canonical
    return aliases


class AssignmentStrategyConfig(BaseModel):
    """Flexible assignment-strategy shape that can parse current and future strategies."""

    model_config = ConfigDict(extra="allow")

    strategy: str
    games: list[str] | None = None
    player_characters: list[str] | None = None
    non_player_characters: list[str] | None = None
    quota_per_game: int | None = None
    max_assignments_per_player: int | None = None
    seed: str | int | None = None
    pc_eligible_only: bool = False
    allow_choice_if_multiple: bool = False
    require_completion: bool = True

    @model_validator(mode="after")
    def reject_removed_policy_fields(self) -> "AssignmentStrategyConfig":
        """Reject assignment policy names that were replaced by explicit booleans."""
        extras = self.__pydantic_extra__ or {}
        removed = {"assignment_mode", "require_assignment_completion"} & set(extras)
        if removed:
            names = ", ".join(sorted(removed))
            raise ValueError(
                f"Removed assignment policy field(s): {names}. "
                "Use allow_choice_if_multiple and require_completion instead."
            )
        return self

    @field_validator("games")
    @classmethod
    def validate_games(cls, values: list[str] | None) -> list[str] | None:
        """Normalize experiment game references when they are supplied."""
        if values is None:
            return None

        aliases = _available_game_names()
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            canonical = aliases.get(_normalize_game_ref(value))
            if canonical is None:
                raise ValueError(f"Unknown game reference in assignment strategy: {value!r}")
            lowered = canonical.lower()
            if lowered in seen:
                raise ValueError(f"Duplicate game listed in assignment strategy: {canonical}")
            seen.add(lowered)
            normalized.append(canonical)
        return normalized


class ExperimentConfig(SerdeMixin, BaseModel):
    """Top-level experiment configuration for assignment-driven studies."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    description: str = ""
    condition: Optional[Literal["learning", "static"]] = None
    assignment_strategy: AssignmentStrategyConfig
    forms: list[ExperimentForm] = Field(default_factory=list)

    @field_validator("forms", mode="before")
    @classmethod
    def normalize_forms(cls, value: Any) -> Any:
        """Accept forms as either a list or a mapping keyed by form name."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [{"name": name, **payload} for name, payload in value.items()]
        raise ValueError("forms must be a list or a mapping of form names to form definitions.")

    @model_validator(mode="after")
    def validate_config(self) -> "ExperimentConfig":
        """Validate strategy-specific constraints and form names."""
        form_names = [form.name for form in self.forms]
        if len(form_names) != len(set(form_names)):
            raise ValueError("Experiment form names must be unique.")
        from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy

        get_assignment_strategy(self.assignment_strategy.strategy).validate_config(config=self)
        return self

    @property
    def games(self) -> list[str]:
        """Canonical list of games included in the experiment assignment strategy."""
        return list(self.assignment_strategy.games or [])

    def forms_for_phase(self, *, before_or_after: str) -> list[ExperimentForm]:
        """Return forms matching one phase."""
        return [form for form in self.forms if form.before_or_after == before_or_after]

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentConfig":
        """Load an experiment config from YAML."""
        return cls.from_yaml(path)
