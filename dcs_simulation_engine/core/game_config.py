"""Base game config module."""

import importlib
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
)

from dcs_simulation_engine.dal.base import (
    DataProvider,
)
from dcs_simulation_engine.utils.serde import SerdeMixin
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    field_validator,
)


class AccessSettings(BaseModel):
    """Defines access settings for the game."""

    model_config = ConfigDict(extra="forbid")
    new_player_form: Optional["Form"] = Field(default=None)
    require_consent_signature: bool = False


class Form(BaseModel):
    """Defines a form structure."""

    model_config = ConfigDict(extra="forbid")
    preamble: Optional[str] = None
    questions: List["FormQuestion"] = Field(default_factory=list)


class FormQuestion(BaseModel):
    """Defines a form structure."""

    model_config = ConfigDict(extra="forbid")
    key: str
    type: Literal[
        "text",
        "textarea",
        "boolean",
        "email",
        "phone",
        "number",
        "select",
        "multiselect",
        "radio",
        "checkboxes",
    ]
    placeholder: Optional[str] = None
    info: Optional[str] = None
    label: Optional[str] = None
    required: bool = False
    pii: bool = False
    options: Optional[List[str]] = None  # for select, multiselect, radio

    @field_validator("key")
    @classmethod
    def key_format(cls, v: str) -> str:
        """Validate key format."""
        if " " in v:
            raise ValueError("Key must not contain spaces.")
        if not all(c.islower() or c == "_" for c in v):
            raise ValueError("Key must be lowercase letters and underscores only.")
        return v


VersionStr = Annotated[
    str,
    constr(
        pattern=(
            r"^(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)"
            r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
        )
    ),
]


class GameConfig(SerdeMixin, BaseModel):
    """Top-level configuration for the game."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    description: str
    version: VersionStr
    authors: Optional[List[str]] = Field(default_factory=lambda: ["DCS"])
    stopping_conditions: Dict[str, Any] = Field(default_factory=dict)
    access_settings: Optional[AccessSettings] = Field(default=None)
    data_collection_settings: dict[str, Any] = Field(default_factory=dict)

    # Dotted import path to the game engine class, e.g.
    # "dcs_simulation_engine.games.explore.ExploreGame"
    game_class: str

    def get_game_class_instance(self) -> Any:
        """Dynamically import and instantiate the game engine class."""
        module_path, class_name = self.game_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()

    @classmethod
    def load(cls, path: Any) -> "GameConfig":
        """Load a GameConfig from a YAML file."""
        return cls.from_yaml(path)

    def is_player_allowed(self, *, player_id: Optional[str], provider: DataProvider) -> bool:
        """Evaluate access policy from declarative access settings."""
        access = self.access_settings
        if not access or not access.require_consent_signature:
            return True
        if not player_id:
            return False

        player = provider.get_player(player_id=player_id)
        if player is None:
            return False

        consent_signature = player.data.get("consent_signature")
        if isinstance(consent_signature, dict):
            answer = consent_signature.get("answer")
            if isinstance(answer, list):
                return any(str(item).strip() for item in answer)
            return bool(answer)
        return bool(consent_signature)

    def get_valid_characters(
        self,
        *,
        player_id: Optional[str] = None,
        provider: DataProvider,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Return (valid_pcs, valid_npcs) as (display_string, hid) tuples."""
        # Character filtering and display formatting are disabled globally.
        _ = player_id
        all_chars = list(provider.get_characters())  # type: ignore[arg-type]
        choices = [(record.hid, record.hid) for record in all_chars]
        return list(choices), list(choices)
