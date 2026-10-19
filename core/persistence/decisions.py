"""Separate user decisions; immutable imported facts remain in the five core tables."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned


class LabelFields:
    name: Mapped[str] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Category(Identity, CreatedAt, Owned, LabelFields, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_categories_owner_id"),
        UniqueConstraint("owner_id", "name", name="uq_categories_name"),
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 120", name="ck_categories_name"
        ),
        CheckConstraint("version > 0", name="ck_categories_version"),
    )


class FundingAccount(Identity, CreatedAt, Owned, LabelFields, Base):
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_accounts_owner_id"),
        UniqueConstraint("owner_id", "name", name="uq_accounts_name"),
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 120", name="ck_accounts_name"
        ),
        CheckConstraint("version > 0", name="ck_accounts_version"),
    )


class EntryDecision(Identity, CreatedAt, Owned, Base):
    __tablename__ = "entry_decisions"
    __table_args__ = (
        UniqueConstraint("owner_id", "entry_id", name="uq_entry_decisions_entry"),
        ForeignKeyConstraint(
            ["owner_id", "entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_decisions_entry",
        ),
        ForeignKeyConstraint(
            ["owner_id", "category_id"],
            ["hisaab.categories.owner_id", "hisaab.categories.id"],
            ondelete="RESTRICT",
            name="fk_decisions_category",
        ),
        ForeignKeyConstraint(
            ["owner_id", "account_id"],
            ["hisaab.accounts.owner_id", "hisaab.accounts.id"],
            ondelete="RESTRICT",
            name="fk_decisions_account",
        ),
        CheckConstraint("version > 0", name="ck_decisions_version"),
    )
    entry_id: Mapped[UUID]
    category_id: Mapped[UUID | None]
    account_id: Mapped[UUID | None]
    overrides: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    acknowledged: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    source_fingerprint: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )


class DecisionEvent(Identity, CreatedAt, Owned, Base):
    __tablename__ = "decision_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_decision_events_entry",
        ),
        UniqueConstraint(
            "owner_id", "entry_id", "version", name="uq_decision_events_version"
        ),
    )
    entry_id: Mapped[UUID]
    version: Mapped[int]
    actor_auth_user_id: Mapped[UUID | None]
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
