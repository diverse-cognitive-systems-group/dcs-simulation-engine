from abc import abstractmethod
from dataclasses import dataclass


@dataclass
class RegisteredUser:
    user_id: str


@dataclass
class LoggedInUser:
    user_id: str
    api_key: str  # new plaintext key issued on login


class DataLayer:
    """Base class for data layer implementations."""

    @abstractmethod
    async def login_user(self, *, email: str, password: str) -> "LoggedInUser | None":
        """Verify email+password, issue a new access key. Returns None on bad credentials."""
        pass

    @abstractmethod
    async def authenticate(self, *, api_key: str) -> str | None:
        """Validate an access key and return its user_id, or None if invalid/revoked."""
        pass

    @abstractmethod
    async def register_user(
        self,
        *,
        password: str | None,
        full_name: str | None,
        email: str | None,
        phone_number: str | None,
        prior_experience: str | None,
        additional_comments: str | None,
        consent_to_followup: list[str] | None,
        consent_signature: list[str] | None,
    ) -> RegisteredUser:
        """Create a user, pii, and auth record. Return user_id and plaintext access key."""
        pass

    @abstractmethod
    async def create_session(self, *, session_id: str, user_id: str, game_name: str) -> None:
        """Persist a new session row to the database."""
        pass

    @abstractmethod
    async def log_message(self, *, session_id: str, role: str, content: str) -> None:
        """Insert a message row (role: 'human' or 'ai') for the given session."""
        pass
