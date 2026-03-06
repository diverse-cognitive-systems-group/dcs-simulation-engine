import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dcs_db.models.base import Base


class Game(Base):
    """A game definition (template), not a running instance."""

    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of strings, e.g. ["Alice Smith", "Bob Jones"]
    authors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    game_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("models.id", ondelete="SET NULL"), nullable=True, index=True
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="game")  # noqa: F821
    default_model: Mapped["Model | None"] = relationship(back_populates="games")  # noqa: F821
