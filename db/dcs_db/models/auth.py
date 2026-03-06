import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dcs_db.models.base import Base


class Auth(Base):
    __tablename__ = "auth"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # bcrypt hash of the user's password
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # plaintext API key (stored to allow reuse on re-login)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # bcrypt hash of the API key for constant-time verification
    api_key_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # First ~8 chars for display (e.g. "sk-abc123...")
    api_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="auth")  # noqa: F821
