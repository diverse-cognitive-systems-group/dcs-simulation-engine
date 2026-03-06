import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dcs_db.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    api_key_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_key_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prior_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stored as JSON array of strings (e.g. ["email", "phone"])
    consent_to_followup: Mapped[list | None] = mapped_column(Text, nullable=True)
    consent_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pii: Mapped["Pii | None"] = relationship(back_populates="user")  # noqa: F821
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        back_populates="player", foreign_keys="Session.player_id"
    )
    auth: Mapped["Auth | None"] = relationship(back_populates="user")  # noqa: F821
