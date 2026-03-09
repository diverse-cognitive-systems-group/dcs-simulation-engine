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
    access_key_hash: Optional[str]
    access_key_prefix: Optional[str]
    data: dict[str, Any]


class RunRecord(NamedTuple):
    """A persisted game run."""

    id: str
    player_id: str
    game_name: str
    created_at: Any
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

    def list_characters(
        self,
        *,
        descriptor: str | None = None,
        exclude_hids: set[str] | None = None,
    ) -> list[CharacterRecord]:
        """Return characters with optional backend-neutral filters."""
        raise NotImplementedError

    def get_player(self, *, player_id: str) -> PlayerRecord | None:
        """Return a single player by id, or None if not found."""
        raise NotImplementedError

    def list_runs(
        self,
        *,
        player_id: str | None = None,
        game_name: str | None = None,
    ) -> list[RunRecord]:
        """Return runs, optionally filtered by player id and/or game name."""
        raise NotImplementedError

    def create_player(
        self,
        *,
        player_data: dict[str, Any],
        player_id: str | None = None,
        issue_access_key: bool = False,
    ) -> tuple[PlayerRecord, str | None]:
        """Create or upsert a player.

        Returns:
            (record, raw_key) where raw_key is None unless issue_access_key=True.
        """
        raise NotImplementedError

    def get_players(self, *, access_key: str | None = None) -> list[PlayerRecord] | PlayerRecord | None:
        """Return all players, or a single player by access key."""
        raise NotImplementedError

    def save_run(
        self,
        player_id: str,
        run_data: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> RunRecord:
        """Persist a game run and return its record."""
        raise NotImplementedError

    def get_runs(self) -> list[RunRecord]:
        """Return all run records."""
        return self.list_runs()

    def upsert_character(self, data: dict[str, Any], *, character_id: str | None = None) -> str:
        """Create or update a character. Returns the character's id string."""
        raise NotImplementedError

    def delete_character(self, character_id: str) -> None:
        """Delete a character by id."""
        raise NotImplementedError

    def delete_player(self, player_id: str) -> None:
        """Delete a player by id."""
        raise NotImplementedError
