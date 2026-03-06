import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dcs_db.models.base import Base


class Model(Base):
    """An LLM model record (e.g. 'gpt-4o', 'qwen/qwen3-4b')."""

    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="model")  # noqa: F821
    games: Mapped[list["Game"]] = relationship(back_populates="default_model")  # noqa: F821
