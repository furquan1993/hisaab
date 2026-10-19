"""Append-only statement coverage/date review snapshots, separate from extraction."""

from datetime import date
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned


class ImportReview(Identity, CreatedAt, Owned, Base):
    __tablename__ = "import_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "import_id"],
            ["hisaab.imports.owner_id", "hisaab.imports.id"],
            ondelete="RESTRICT",
            name="fk_import_reviews_root",
        ),
        ForeignKeyConstraint(
            ["owner_id", "reviewed_import_id"],
            ["hisaab.imports.owner_id", "hisaab.imports.id"],
            ondelete="RESTRICT",
            name="fk_import_reviews_source",
        ),
        UniqueConstraint(
            "owner_id", "import_id", "version", name="uq_import_reviews_version"
        ),
        CheckConstraint("version>0", name="ck_import_reviews_version"),
    )
    import_id: Mapped[UUID]
    reviewed_import_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    source_fingerprint: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[list] = mapped_column(JSON)
    statement_date_override: Mapped[date | None]
    reason: Mapped[str] = mapped_column(Text)
    actor_auth_user_id: Mapped[UUID | None]
