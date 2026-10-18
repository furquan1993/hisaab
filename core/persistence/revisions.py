"""Immutable source-version provenance and reviewed logical entry bindings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned


class ParserRevision(Identity, CreatedAt, Owned, Base):
    __tablename__ = "parser_revisions"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_revisions_owner_id"),
        UniqueConstraint(
            "owner_id",
            "candidate_import_id",
            "version",
            name="uq_revisions_candidate_version",
        ),
        ForeignKeyConstraint(
            ["owner_id", "statement_id", "candidate_import_id"],
            [
                "hisaab.imports.owner_id",
                "hisaab.imports.statement_id",
                "hisaab.imports.id",
            ],
            ondelete="RESTRICT",
            name="fk_revisions_candidate",
        ),
        ForeignKeyConstraint(
            ["owner_id", "statement_id", "base_import_id"],
            [
                "hisaab.imports.owner_id",
                "hisaab.imports.statement_id",
                "hisaab.imports.id",
            ],
            ondelete="RESTRICT",
            name="fk_revisions_base",
        ),
        CheckConstraint(
            "status IN ('pending','accepted','rejected')", name="ck_revisions_status"
        ),
        CheckConstraint("version>0", name="ck_revisions_version"),
    )
    statement_id: Mapped[UUID]
    base_import_id: Mapped[UUID | None]
    candidate_import_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        Text, default="pending", server_default="pending"
    )
    plan: Mapped[dict] = mapped_column(JSON)
    reviewed_mapping: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_auth_user_id: Mapped[UUID | None]


class EntryLink(Identity, CreatedAt, Owned, Base):
    __tablename__ = "entry_links"
    __table_args__ = (
        UniqueConstraint("owner_id", "entry_id", name="uq_entry_links_entry"),
        UniqueConstraint(
            "import_id", "logical_entry_id", name="uq_entry_links_logical"
        ),
        ForeignKeyConstraint(
            ["owner_id", "import_id", "entry_id"],
            [
                "hisaab.entries.owner_id",
                "hisaab.entries.import_id",
                "hisaab.entries.id",
            ],
            ondelete="RESTRICT",
            name="fk_entry_links_source",
        ),
        ForeignKeyConstraint(
            ["owner_id", "logical_entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_entry_links_logical",
        ),
        ForeignKeyConstraint(
            ["owner_id", "revision_id"],
            ["hisaab.parser_revisions.owner_id", "hisaab.parser_revisions.id"],
            ondelete="RESTRICT",
            name="fk_entry_links_revision",
        ),
    )
    import_id: Mapped[UUID]
    entry_id: Mapped[UUID]
    logical_entry_id: Mapped[UUID]
    revision_id: Mapped[UUID]
