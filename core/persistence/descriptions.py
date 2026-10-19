"""Append-only friendly descriptions, independent of financial decision versions."""
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned


class EntryDescription(Identity, CreatedAt, Owned, Base):
    __tablename__ = "entry_descriptions"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_entry_descriptions_entry"),
        UniqueConstraint("owner_id", "entry_id", "version", name="uq_entry_descriptions_version"),
        CheckConstraint("version>0", name="ck_entry_descriptions_version"),
        CheckConstraint("description IS NULL OR length(btrim(description)) BETWEEN 1 AND 500", name="ck_entry_descriptions_text"),
    )
    entry_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    actor_auth_user_id: Mapped[UUID | None]
