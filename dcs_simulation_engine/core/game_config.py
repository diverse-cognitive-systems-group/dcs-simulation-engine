"""Base game config module."""

# TODO: part of config that queries db using raw dict-like queries is
# janky and should be replaced with something more robust.

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    field_validator,
    model_validator,
)

from dcs_simulation_engine.core.simulation_graph import GraphConfig
from dcs_simulation_engine.helpers import database_helpers as dbh
from dcs_simulation_engine.utils.serde import SerdeMixin


class ValiditySelector(BaseModel):
    """Defines a database query for selecting characters."""

    model_config = ConfigDict(extra="forbid")
    valid: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    invalid: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _at_least_one_non_empty(self) -> "ValiditySelector":
        if not self.valid and not self.invalid:
            raise ValueError("Provide at least one of 'valid' or 'invalid'.")
        return self

    @field_validator("valid", "invalid", mode="before")
    @classmethod
    def _none_to_empty_dict(cls, v: Any) -> Any:
        if v is None:
            return {}
        return v

    # 1) Guard allowed collections
    @field_validator("valid", "invalid", mode="before")
    @classmethod
    def check_sources(cls, v: Any) -> Any:
        """Validate that only allowed collection names are used."""
        ALLOWED_SOURCES = {"players", "runs", "characters"}
        if not isinstance(v, dict):
            raise ValueError("Must be a mapping of {collection_name: query_dict}.")
        unknown = set(v) - ALLOWED_SOURCES
        if unknown:
            raise ValueError(
                f"Unknown collection(s): {sorted(unknown)}. "
                f"Allowed: {sorted(ALLOWED_SOURCES)}"
            )
        for k, q in v.items():
            if not isinstance(q, dict):
                raise ValueError(f"Query for '{k}' must be a dict.")
        return v

    # 2) Optional server-side validation hook
    def validate_on_server(self) -> None:
        """Validate queries against the database server.

        Throws if any query is invalid.
        """

        def check_map(m: dict[str, Dict[str, Any]]) -> None:
            for coll, query in (m or {}).items():
                dbh.validate_query_against_server(coll, query)

        check_map(self.valid)
        check_map(self.invalid)


class AccessSettings(BaseModel):
    """Defines access settings for the game."""

    model_config = ConfigDict(extra="forbid")
    user: ValiditySelector
    new_player_form: Optional[Form] = Field(default=None)


class Form(BaseModel):
    """Defines a form structure."""

    model_config = ConfigDict(extra="forbid")
    preamble: Optional[str] = None
    questions: List[FormQuestion] = Field(default_factory=list)


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
    options: Optional[List[str]] = None  # for select, multiselect, radio,

    # validate that key has no spaces and is lowercase with underscores
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
    """Defines the player and non-player character selection logic."""

    model_config = ConfigDict(extra="forbid")
    pc: ValiditySelector
    npc: ValiditySelector
    display_pc_choice_as: Optional[str] = "{hid}"
    display_npc_choice_as: Optional[str] = "{hid}"


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

    # Metadata
    name: str
    description: str
    version: VersionStr
    authors: Optional[List[str]] = Field(default_factory=lambda: ["DCS"])

    # Stopping conditions
    stopping_conditions: Dict[str, Any] = Field(default_factory=dict)

    # State overrides
    state_overrides: Dict[str, Any] = Field(default_factory=dict)

    # Access settings
    access_settings: AccessSettings

    # Data collection settings
    data_collection_settings: dict[str, Any] = Field(default_factory=dict)

    # Character settings
    character_settings: CharacterSettings

    graph_config: GraphConfig

    def validate_mongo_queries(self) -> None:
        """Call server-side validation on all embedded selectors."""
        logger.debug("Validating MongoDB queries against server...")
        self.access_settings.user.validate_on_server()
        self.character_settings.pc.validate_on_server()
        self.character_settings.npc.validate_on_server()

    def get_valid_characters(
        self, player_id: Optional[str] = None, return_formatted: Optional[bool] = False
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Get valid PC/NPC character hids.

        For each selector (PC and NPC):
        •	UNION all results from valid-where → V
        •	UNION all results from invalid-where → I
        •	Final = V - I (set difference)

        For each selector: UNION(valid-where) - UNION(invalid-where)
        """

        def fetch_union(where_map: Optional[dict[str, Any]]) -> set[str]:
            if not where_map:
                return set()
            acc: set[str] = set()
            for source, where in where_map.items():
                hids = dbh.list_characters_where(
                    player_id=player_id or None, query=where, collection=source
                )
                acc.update(hids)
            return acc

        # PCs
        pc_valid = fetch_union(getattr(self.character_settings.pc, "valid", {}))
        pc_invalid = fetch_union(getattr(self.character_settings.pc, "invalid", {}))
        final_pcs = pc_valid - pc_invalid
        logger.debug(
            f"PCs: |V|={len(pc_valid)} |I|={len(pc_invalid)} |V-I|={len(final_pcs)}"
        )

        # NPCs
        npc_valid = fetch_union(getattr(self.character_settings.npc, "valid", {}))
        npc_invalid = fetch_union(getattr(self.character_settings.npc, "invalid", {}))
        final_npcs = npc_valid - npc_invalid
        logger.debug(
            f"NPCs: |V|={len(npc_valid)} |I|={len(npc_invalid)} |V-I|={len(final_npcs)}"
        )

        # Return deterministic lists (sorted) or randomize upstream as needed
        sorted_pcs = sorted(final_pcs)
        sorted_npcs = sorted(final_npcs)
        if not return_formatted:
            return sorted_pcs, sorted_npcs

        # Format character choices according to config
        pc_fmt = getattr(self.character_settings, "display_pc_choice_as", "{hid}")
        npc_fmt = getattr(self.character_settings, "display_npc_choice_as", "{hid}")

        def format_characters(hids: list[str], fmt: str) -> list[str]:
            """Format character choices according to fmt string."""
            formatted: list[str] = []

            for hid in hids:
                try:
                    doc = dbh.get_character_from_hid(hid)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(f"Failed to load character for hid={hid}: {exc}")
                    formatted.append(hid)
                    continue

                if not doc:
                    formatted.append(hid)
                    continue

                # Build a formatting context
                context: dict[str, Any] = {"hid": hid}

                # Support dict-like or pydantic-like objects
                if isinstance(doc, dict):
                    context.update(doc)
                else:
                    if hasattr(doc, "dict") and callable(getattr(doc, "dict")):
                        context.update(doc.dict())
                    else:
                        # Last resort: use __dict__ if available
                        context.update(getattr(doc, "__dict__", {}))

                try:
                    formatted.append(str(fmt).format(**context))
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        f"Failed to format character choice for hid={hid} "
                        f"with fmt={fmt!r}: {exc}"
                    )
                    formatted.append(hid)

            return formatted

        formatted_pcs = format_characters(sorted_pcs, pc_fmt)
        formatted_npcs = format_characters(sorted_npcs, npc_fmt)

        # update this to return a list of tuples with formatted string and hid)
        return list(zip(formatted_pcs, sorted_pcs)), list(
            zip(formatted_npcs, sorted_npcs)
        )

    def is_player_allowed(self, player_id: Optional[str]) -> bool:
        """Check access via UNION(valid) − UNION(invalid) over `access_settings.user`.

        Empty maps mean “no restriction”. If BOTH valid and invalid are empty,
        allow any player (including None).

        Additionally: any collection with an EMPTY query (e.g. {}) matches everyone.
        """
        sel = self.access_settings.user
        valid_map = getattr(sel, "valid", {}) or {}
        invalid_map = getattr(sel, "invalid", {}) or {}

        logger.debug(
            f"is_player_allowed called with valid_map={valid_map},"
            f" invalid_map={invalid_map}"
        )

        # If both sides are empty → no restriction → allow anyone.
        if not valid_map and not invalid_map:
            logger.debug(
                "is_player_allowed: no restrictions (valid/invalid empty) -> allow"
            )
            return True

        def any_empty_query(m: dict[Any, Any]) -> bool:
            """Return True if any query in the map is empty (matches everyone)."""
            return any(not q for q in m.values())

        # ----- VALID -----
        if not valid_map:
            logger.debug("is_player_allowed: valid map empty -> allow")
            in_valid = True
        elif any_empty_query(valid_map):
            logger.debug("is_player_allowed: valid map has empty query -> allow")
            in_valid = True
        else:
            # Need a concrete player to test non-empty restrictions.
            if not player_id:
                logger.debug(
                    "is_player_allowed: valid map has non-empty queries "
                    "but no player_id -> deny"
                )
                return False
            in_valid = any(
                dbh.user_matches_where(player_id=player_id, query=q, collection=src)
                for src, q in valid_map.items()
            )

        # ----- INVALID -----
        if not invalid_map:
            # Empty => no restriction to exclude => treat as False
            in_invalid = False
        elif any_empty_query(invalid_map):
            # Any empty query means "everyone is invalid" (excluded),
            # regardless of player_id
            in_invalid = True
        else:
            # If no player_id, we can’t be in an invalid set scoped to a player.
            in_invalid = (
                False
                if not player_id
                else any(
                    dbh.user_matches_where(player_id=player_id, query=q, collection=src)
                    for src, q in invalid_map.items()
                )
            )

        allowed = in_valid and not in_invalid
        logger.debug(
            f"is_player_allowed: player_id={player_id} -> "
            f"valid={in_valid} invalid={in_invalid} allowed={allowed}"
        )
        return allowed
