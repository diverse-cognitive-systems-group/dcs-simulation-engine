import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dcs_db.models.base import Base


class Session(Base):
    """A single play session - an instance of a game."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("games.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pc_character_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    npc_character_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lifecycle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stopping_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scratchpad: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    game: Mapped["Game"] = relationship(back_populates="sessions")  # noqa: F821
    player: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="sessions", foreign_keys=[player_id]
    )
    pc_character: Mapped["Character | None"] = relationship(  # noqa: F821
        foreign_keys=[pc_character_id]
    )
    npc_character: Mapped["Character | None"] = relationship(  # noqa: F821
        foreign_keys=[npc_character_id]
    )
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="session", cascade="all, delete-orphan", order_by="Message.timestamp"
    )
    feedback: Mapped[list["Feedback"]] = relationship(  # noqa: F821
        back_populates="session", cascade="all, delete-orphan"
    )
