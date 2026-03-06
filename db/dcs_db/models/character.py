import uuid

from sqlalchemy import JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from dcs_db.models.base import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Human-readable unique identifier (e.g. "flatworm-01")
    hid: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    inclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of strings, e.g. ["curious", "timid", "empathetic"]
    common_descriptors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    abilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    anthronormal_divergence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    interaction_examples: Mapped[list | None] = mapped_column(JSON, nullable=True)
