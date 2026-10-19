"""Private history and explicit corrections used for independent label matching."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKeyConstraint, Index,
    Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned


class AssignmentExample(Identity, CreatedAt, Owned, Base):
    __tablename__ = "assignment_examples"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "source_key", "kind", name="uq_assignment_examples_source"
        ),
        ForeignKeyConstraint(
            ["owner_id", "entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT", name="fk_assignment_examples_entry",
        ),
        ForeignKeyConstraint(
            ["owner_id", "account_id"],
            ["hisaab.accounts.owner_id", "hisaab.accounts.id"],
            ondelete="RESTRICT", name="fk_assignment_examples_account",
        ),
        ForeignKeyConstraint(
            ["owner_id", "category_id"],
            ["hisaab.categories.owner_id", "hisaab.categories.id"],
            ondelete="RESTRICT", name="fk_assignment_examples_category",
        ),
        CheckConstraint(
            "kind IN ('account','category')", name="ck_assignment_examples_kind"
        ),
        CheckConstraint(
            "direction IN ('debit','credit') OR (is_manual AND direction='unknown')",
            name="ck_assignment_examples_direction",
        ),
        CheckConstraint(
            "(kind='account' AND category_id IS NULL) OR "
            "(kind='category' AND account_id IS NULL)",
            name="ck_assignment_examples_label",
        ),
        CheckConstraint(
            "is_manual = (entry_id IS NOT NULL)", name="ck_assignment_examples_manual"
        ),
        Index(
            "ix_assignment_examples_match", "owner_id", "merchant_key", "direction", "kind"
        ),
    )
    source_key: Mapped[str] = mapped_column(Text)
    merchant_key: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    is_manual: Mapped[bool] = mapped_column(Boolean)
    entry_id: Mapped[UUID | None]
    account_id: Mapped[UUID | None]
    category_id: Mapped[UUID | None]
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
