"""Run configuration models and static validation helpers."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dcs_simulation_engine.core.forms import Form
from dcs_simulation_engine.utils.serde import SerdeMixin
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RunConfigUI(BaseModel):
    """User-interface options for a run."""

    model_config = ConfigDict(extra="forbid")

    launch_gui: bool = True
    registration_required: bool = True


class RunConfigHumans(BaseModel):
    """Human-player admission policy for a run."""

    model_config = ConfigDict(extra="forbid")

    all: bool = True


class RunConfigModelPlayer(BaseModel):
    """One model player configured for a headless run."""

    model_config = ConfigDict(extra="forbid")

    id: str


class RunConfigPlayers(BaseModel):
    """Player populations allowed or executed by a run."""

    model_config = ConfigDict(extra="forbid")

    humans: RunConfigHumans = Field(default_factory=RunConfigHumans)
    models: list[RunConfigModelPlayer] = Field(default_factory=list)


class RunConfigGame(BaseModel):
    """One game included in a run, plus game-owned overrides."""

    model_config = ConfigDict(extra="forbid")

    name: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class RunConfigStrategy(BaseModel):
    """Assignment strategy selector plus strategy-specific parameters."""

    model_config = ConfigDict(extra="allow")

    id: str


class RunConfigNextGameStrategy(BaseModel):
    """Next-game assignment strategy configuration."""

    model_config = ConfigDict(extra="forbid")

    strategy: RunConfigStrategy


class RunConfig(SerdeMixin, BaseModel):
    """Top-level run configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    seed: int | None = None
    ui: RunConfigUI = Field(default_factory=RunConfigUI)
    players: RunConfigPlayers = Field(default_factory=RunConfigPlayers)
    games: list[RunConfigGame] = Field(default_factory=list)
    next_game_strategy: RunConfigNextGameStrategy
    forms: list[Form] = Field(default_factory=list)

    @field_validator("forms", mode="before")
    @classmethod
    def normalize_forms(cls, value: Any) -> Any:
        """Accept null forms and mapping-style form declarations."""
        if value is None:
            return []
        if isinstance(value, dict):
            value = [{"name": name, **payload} for name, payload in value.items()]
        if not isinstance(value, list):
            raise ValueError("forms must be null, a list, or a mapping of form names to definitions.")
        return value

    @model_validator(mode="after")
    def validate_forms(self) -> "RunConfig":
        """Fail loudly when form names collide after normalization."""
        form_names = [form.name for form in self.forms]
        if len(form_names) != len(set(form_names)):
            raise ValueError("Run config form names must be unique.")
        return self

    @classmethod
    def load(cls, path: str | Path) -> "RunConfig":
        """Load a run config from YAML."""
        return cls.from_yaml(path)

    def forms_for_trigger(self, trigger: str | None = None, *, event: str | None = None) -> list[Form]:
        """Return forms matching one trigger event string."""
        event_name = event if event is not None else trigger
        return [form for form in self.forms if form.trigger.event == event_name]

    def form_groups_for_trigger(self, *, event: str) -> list[dict[str, Any]]:
        """Return configured form groups for one trigger event."""
        forms = self.forms_for_trigger(event)
        if not forms:
            return []
        return [
            {
                "trigger": {"event": event, "match": None},
                "forms": forms,
            }
        ]

    @property
    def assignment_strategy(self) -> SimpleNamespace:
        """Expose the existing assignment-strategy view for run configs."""
        strategy = self.next_game_strategy.strategy
        values = strategy.model_dump()
        values["strategy"] = values.pop("id")
        values["games"] = self.game_names
        values.setdefault("player_characters", None)
        values.setdefault("non_player_characters", None)
        values.setdefault("quota_per_game", None)
        values.setdefault("max_assignments_per_player", None)
        values.setdefault("seed", self.seed)
        values.setdefault("pc_eligible_only", False)
        values.setdefault("allow_choice_if_multiple", False)
        values.setdefault("require_completion", True)
        return SimpleNamespace(**values)

    @property
    def registration_required(self) -> bool:
        """Return whether human players must register before playing."""
        return self.ui.registration_required

    @property
    def has_model_players(self) -> bool:
        """Return whether the run config includes model players."""
        return bool(self.players.models)

    @property
    def game_names(self) -> list[str]:
        """Return configured game names in declaration order."""
        return [game.name for game in self.games]


def validate_run_config_references(config: RunConfig) -> None:
    """Validate static references in a run config without runtime side effects."""
    from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
    from dcs_simulation_engine.core.session_manager import SessionManager

    get_assignment_strategy(config.next_game_strategy.strategy.id).validate_config(config=config)

    for game in config.games:
        game_config = SessionManager.get_game_config_cached(game.name)
        game_cls = game_config.get_game_class()
        game_cls.parse_overrides(game.overrides)
