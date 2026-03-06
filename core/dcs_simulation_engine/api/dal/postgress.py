import json
import logging
import secrets
import uuid
from datetime import UTC, datetime

import bcrypt
from dcs_db.engine import get_session
from dcs_db.models.auth import Auth
from dcs_db.models.game import Game
from dcs_db.models.message import Message
from dcs_db.models.pii import Pii
from dcs_db.models.session import Session as DBSession
from dcs_db.models.user import User
from sqlalchemy import select

from dcs_simulation_engine.api.dal.base import DataLayer, LoggedInUser, RegisteredUser

logger = logging.getLogger(__name__)


def _hash(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def _verify(secret: str, hashed: str) -> bool:
    return bcrypt.checkpw(secret.encode(), hashed.encode())


def _is_key_valid(auth: Auth) -> bool:
    """Return True if the auth record has an unexpired, unrevoked api key."""
    if not auth.api_key_hash or auth.revoked_at is not None:
        return False
    if auth.last_used_at and (datetime.now(UTC) - auth.last_used_at).total_seconds() > 6 * 60 * 60:
        return False
    return True


class PGDataLayer(DataLayer):

    async def login_user(self, *, email: str, password: str) -> LoggedInUser | None:
        async with get_session() as db:
            # Look up user by email via pii table
            row = await db.execute(
                select(Pii).where(Pii.email == email)
            )
            pii = row.scalars().first()
            if pii is None:
                return None

            # Load auth record
            auth_row = await db.execute(
                select(Auth).where(Auth.user_id == pii.user_id)
            )
            auth = auth_row.scalars().first()
            if auth is None or auth.password_hash is None:
                return None

            if not _verify(password, auth.password_hash):
                return None

            user_row = await db.execute(select(User).where(User.id == pii.user_id))
            user = user_row.scalars().first()
            if user is None:
                return None

            # Reuse existing key if still valid
            if _is_key_valid(auth) and auth.api_key:
                auth.last_used_at = datetime.now(UTC)
                return LoggedInUser(user_id=str(pii.user_id), api_key=auth.api_key)

            # Issue a new access key
            api_key = secrets.token_urlsafe(32)
            now = datetime.now(UTC)
            auth.api_key = api_key
            auth.api_key_hash = _hash(api_key)
            auth.api_key_prefix = api_key[:8]
            auth.last_used_at = now
            user.last_key_issued_at = now

        return LoggedInUser(user_id=str(pii.user_id), api_key=api_key)

    async def authenticate(self, *, api_key: str) -> str | None:
        if len(api_key) < 8:
            return None

        async with get_session() as db:
            row = await db.execute(
                select(Auth).where(Auth.api_key_prefix == api_key[:8], Auth.revoked_at.is_(None))
            )
            auth = None
            for candidate in row.scalars().all():
                if candidate.api_key_hash and _verify(api_key, candidate.api_key_hash):
                    if not _is_key_valid(candidate):
                        return None
                    auth = candidate
                    break
            if auth is None:
                return None

            user_row = await db.execute(select(User).where(User.id == auth.user_id))
            user = user_row.scalars().first()
            if user is None or user.api_key_revoked:
                return None

            auth.last_used_at = datetime.now(UTC)
            return str(auth.user_id)

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
        consent_signature:  bool | None,
    ) -> RegisteredUser:

        async with get_session() as db:
            user = User(
                last_key_issued_at=None,
                prior_experience=prior_experience,
                additional_comments=additional_comments,
                consent_to_followup=json.dumps(consent_to_followup) if consent_to_followup else None,
                consent_signature=consent_signature if consent_signature else False,
            )
            db.add(user)
            await db.flush()  # populate user.id before inserting related rows

            db.add(Pii(
                user_id=user.id,
                full_name=full_name,
                email=email,
                phone_number=phone_number,
            ))

            db.add(Auth(
                user_id=user.id,
                password_hash=_hash(password) if password else None,
                api_key_hash=None,
                api_key_prefix=None,
                created_at=None,
            ))

        return RegisteredUser(user_id=str(user.id))

    async def create_session(self, *, session_id: str, user_id: str, game_name: str) -> None:
        async with get_session() as db:
            row = await db.execute(select(Game).where(Game.name == game_name))
            game = row.scalars().first()
            if game is None:
                raise ValueError(f"No game found with name {game_name!r}")
            db.add(DBSession(id=uuid.UUID(session_id), player_id=uuid.UUID(user_id), game_id=game.id))

    async def log_message(self, *, session_id: str, role: str, content: str) -> None:
        async with get_session() as db:
            db.add(Message(session_id=uuid.UUID(session_id), role=role, content=content))
