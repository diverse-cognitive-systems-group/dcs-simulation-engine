"""DAL base: record types and DataProvider interface."""

from typing import Any, NamedTuple, Optional


class CharacterRecord(NamedTuple):
    """A character loaded from the data store."""

    hid: str
    name: str
    short_description: str
    data: dict[str, Any]


class PlayerRecord(NamedTuple):
    """A player record (non-PII fields only)."""

    id: str
    created_at: Any
    access_key: Optional[str]
    data: dict[str, Any]


class SessionRecord(NamedTuple):
    """A persisted chat session header record."""

    session_id: str
    player_id: str | None
    game_name: str
    status: str
    created_at: Any
    data: dict[str, Any]


class SessionEventRecord(NamedTuple):
    """A persisted event row for a session transcript."""

    session_id: str
    seq: int
    event_id: str
    event_ts: Any
    direction: str
    event_type: str
    event_source: str
    content: str
    data: dict[str, Any]


class RunRecord(NamedTuple):
    """A persisted run metadata record."""

    name: str
    created_at: Any
    updated_at: Any
    data: dict[str, Any]


class PlayerFormsRecord(NamedTuple):
    """Before-play form responses for a player in a specific run."""

    player_id: str
    run_name: str
    data: dict[str, Any]
    created_at: Any
    updated_at: Any


class AssignmentRecord(NamedTuple):
    """A persisted run assignment row."""

    assignment_id: str
    run_name: str
    player_id: str
    game_name: str
    pc_hid: str
    npc_hid: str
    status: str
    assigned_at: Any
    data: dict[str, Any]


class DataProvider:
    """Abstract data provider interface.

    Subclasses implement storage-specific logic. All methods raise
    NotImplementedError by default.
    """

    def get_character(self, *, hid: str) -> CharacterRecord:
        """Return the character with the given HID.

        Raises:
            ValueError: If no character with that HID exists.
        """
        return self.get_characters(hid=hid)

    def get_characters(self, *, hid: str | None = None) -> list[CharacterRecord] | CharacterRecord:
        """Return all characters, or a single character if hid is given."""
        raise NotImplementedError

    def list_characters(self) -> list[CharacterRecord]:
        """Return all characters."""
        raise NotImplementedError

    def get_player(self, *, player_id: str) -> PlayerRecord | None:
        """Return a single player by id, or None if not found."""
        raise NotImplementedError

    def create_player(
        self,
        *,
        player_data: dict[str, Any],
        player_id: str | None = None,
        issue_access_key: bool = False,
        access_key: str | None = None,
    ) -> tuple[PlayerRecord, str | None]:
        """Create or upsert a player.

        Returns:
            (record, raw_key) where raw_key is None unless an access key was issued or explicitly provided.
        """
        raise NotImplementedError

    def get_players(self, *, access_key: str | None = None) -> list[PlayerRecord] | PlayerRecord | None:
        """Return all players, or a single player by access key."""
        raise NotImplementedError

    def upsert_character(self, data: dict[str, Any], *, character_id: str | None = None) -> str:
        """Create or update a character. Returns the character's id string."""
        raise NotImplementedError

    def delete_character(self, character_id: str) -> None:
        """Delete a character by id."""
        raise NotImplementedError

    def delete_player(self, player_id: str) -> None:
        """Delete a player by id."""
        raise NotImplementedError

    def get_session(self, *, session_id: str, player_id: str | None) -> SessionRecord | None:
        """Return one persisted session header for a player."""
        raise NotImplementedError

    def save_runtime_state(self, *, session_id: str, runtime_state: dict[str, Any]) -> None:
        """Upsert the resumable runtime snapshot on a session document."""
        raise NotImplementedError

    def branch_session(
        self,
        *,
        session_id: str,
        player_id: str | None,
        branched_at: Any,
    ) -> SessionRecord:
        """Clone a persisted session into a new paused child session."""
        raise NotImplementedError

    def get_resumable_session(
        self,
        *,
        player_id: str,
        game_name: str,
        pc_hid: str,
        npc_hid: str,
    ) -> SessionRecord | None:
        """Return the most recent paused session for this player/game/character combo, or None."""
        raise NotImplementedError

    def list_session_events(self, *, session_id: str) -> list[SessionEventRecord]:
        """Return ordered persisted events for a session."""
        raise NotImplementedError

    def append_session_event(
        self,
        *,
        session_id: str,
        player_id: str | None,
        direction: str,
        event_type: str,
        event_source: str,
        content: str,
        content_format: str,
        turn_index: int,
        visible_to_user: bool,
    ) -> SessionEventRecord | None:
        """Append one owned session event to an existing persisted session."""
        raise NotImplementedError

    def set_session_event_feedback(
        self,
        *,
        session_id: str,
        player_id: str | None,
        event_id: str,
        feedback: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Store feedback on a persisted NPC-message event."""
        raise NotImplementedError

    def clear_session_event_feedback(
        self,
        *,
        session_id: str,
        player_id: str | None,
        event_id: str,
    ) -> bool:
        """Remove feedback from a persisted NPC-message event."""
        raise NotImplementedError

    def get_run(self, *, run_name: str) -> RunRecord | None:
        """Return a persisted run record by name."""
        raise NotImplementedError

    def upsert_run(
        self,
        *,
        run_name: str,
        description: str,
        config_snapshot: dict[str, Any],
        progress: dict[str, Any],
    ) -> RunRecord:
        """Create or update a persisted run metadata record."""
        raise NotImplementedError

    def set_run_progress(
        self,
        *,
        run_name: str,
        progress: dict[str, Any],
    ) -> RunRecord | None:
        """Persist the latest run progress snapshot."""
        raise NotImplementedError

    def create_assignment(self, *, assignment_doc: dict[str, Any], allow_concurrent: bool = False) -> AssignmentRecord:
        """Persist a new run assignment row."""
        raise NotImplementedError

    def get_assignment(self, *, assignment_id: str) -> AssignmentRecord | None:
        """Return one assignment row by assignment id."""
        raise NotImplementedError

    def get_active_assignment(self, *, run_name: str, player_id: str) -> AssignmentRecord | None:
        """Return the current active assignment for one player in one run."""
        raise NotImplementedError

    def get_latest_run_assignment_for_player(self, *, player_id: str) -> AssignmentRecord | None:
        """Return the newest run assignment for one player across runs."""
        raise NotImplementedError

    def list_assignments(
        self,
        *,
        run_name: str,
        player_id: str | None = None,
        statuses: list[str] | None = None,
        game_name: str | None = None,
    ) -> list[AssignmentRecord]:
        """List run assignments matching the provided filters."""
        raise NotImplementedError

    def update_assignment_status(
        self,
        *,
        assignment_id: str,
        status: str,
        active_session_id: str | None = None,
    ) -> AssignmentRecord | None:
        """Update assignment status and lifecycle timestamps."""
        raise NotImplementedError

    def set_assignment_form_response(
        self,
        *,
        assignment_id: str,
        form_key: str,
        response: dict[str, Any],
    ) -> AssignmentRecord | None:
        """Store one run form response payload on an assignment row."""
        raise NotImplementedError

    def set_player_form_response(
        self,
        *,
        player_id: str,
        run_name: str,
        form_key: str,
        response: dict[str, Any],
    ) -> PlayerFormsRecord | None:
        """Store one player-scoped form response in the forms collection."""
        raise NotImplementedError

    def get_player_forms(
        self,
        *,
        player_id: str,
        run_name: str,
    ) -> PlayerFormsRecord | None:
        """Return player-scoped form responses for a player in a run."""
        raise NotImplementedError
