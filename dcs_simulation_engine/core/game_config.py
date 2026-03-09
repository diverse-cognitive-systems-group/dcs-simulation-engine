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
    CharacterRecord,
    DataProvider,
)
from dcs_simulation_engine.utils.serde import SerdeMixin
from loguru import logger
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


class CharacterSettings(BaseModel):
    """Defines display formatting for character choices."""

    model_config = ConfigDict(extra="forbid")
    display_pc_choice_as: Optional[str] = "{hid}"
    display_npc_choice_as: Optional[str] = "{hid}"


class CharacterSelector(BaseModel):
    """Selector policy for either PC or NPC character pools."""

    model_config = ConfigDict(extra="forbid")
    descriptor: Optional[str] = None
    include_hids: List[str] = Field(default_factory=list)
    exclude_hids: List[str] = Field(default_factory=list)
    exclude_seen_for_game: Optional[str] = None


class CharacterSelection(BaseModel):
    """Combined selection policy for PC and NPC pools."""

    model_config = ConfigDict(extra="forbid")
    pc: CharacterSelector = Field(default_factory=CharacterSelector)
    npc: CharacterSelector = Field(default_factory=CharacterSelector)


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
    character_settings: Optional[CharacterSettings] = Field(default=None)
    character_selection: CharacterSelection = Field(default_factory=CharacterSelection)

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

    def _select_characters(
        self,
        *,
        selector: CharacterSelector,
        provider: DataProvider,
        player_id: Optional[str],
    ) -> List[CharacterRecord]:
        if selector.descriptor:
            selected: List[CharacterRecord] = list(provider.list_characters(descriptor=selector.descriptor))
        else:
            selected = list(provider.get_characters())  # type: ignore[arg-type]

        if selector.include_hids:
            include = set(selector.include_hids)
            selected = [c for c in selected if c.hid in include]

        if selector.exclude_hids:
            exclude = set(selector.exclude_hids)
            selected = [c for c in selected if c.hid not in exclude]

        if selector.exclude_seen_for_game and player_id:
            seen: set[str] = set()
            runs = provider.list_runs(player_id=player_id, game_name=selector.exclude_seen_for_game)
            for run in runs:
                npc_hid = run.data.get("npc_hid")
                if isinstance(npc_hid, str) and npc_hid:
                    seen.add(npc_hid)
            selected = [c for c in selected if c.hid not in seen]

        return selected

    def get_valid_characters(
        self,
        *,
        player_id: Optional[str] = None,
        provider: DataProvider,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Return (valid_pcs, valid_npcs) as (display_string, hid) tuples."""
        selection = self.character_selection
        pcs = self._select_characters(selector=selection.pc, provider=provider, player_id=player_id)
        npcs = self._select_characters(selector=selection.npc, provider=provider, player_id=player_id)
        logger.debug(f"PCs: {len(pcs)}, NPCs: {len(npcs)}")
        pc_fmt = (self.character_settings.display_pc_choice_as if self.character_settings else None) or "{hid}"
        npc_fmt = (self.character_settings.display_npc_choice_as if self.character_settings else None) or "{hid}"

        def fmt_list(chars: List[CharacterRecord], fmt: str) -> List[Tuple[str, str]]:
            result: List[Tuple[str, str]] = []
            for record in chars:
                context: dict[str, Any] = {"hid": record.hid}
                context.update(record._asdict())
                context.update(record.data)
                try:
                    display = str(fmt).format(**context)
                except Exception as exc:
                    logger.warning(f"Failed to format character choice for hid={record.hid!r}: {exc}")
                    display = record.hid
                result.append((display, record.hid))
            return result

        return fmt_list(pcs, pc_fmt), fmt_list(npcs, npc_fmt)
