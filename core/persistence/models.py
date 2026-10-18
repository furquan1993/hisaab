"""Approved five-entity model. IDs are stable; parser facts remain separate.

Mapped columns / composite constraints:
https://docs.sqlalchemy.org/en/21/orm/declarative_tables.html
https://docs.sqlalchemy.org/en/21/core/constraints.html
"""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from core.persistence.base import SCHEMA, Base, CreatedAt, Identity, Owned


class Owner(Identity, CreatedAt, Base):
    __tablename__ = "owners"
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("auth_user_id", name="uq_owners_auth_user_id"),)
    # Optional provider subject, not the financial Owner ID or an auth-schema FK.
    auth_user_id: Mapped[UUID | None]
    cards: Mapped[list["Card"]] = relationship(viewonly=True, lazy="raise")


class Card(Identity, CreatedAt, Owned, Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_cards_owner_id"),
        CheckConstraint(
            "last_four IS NULL OR length(last_four) = 4", name="ck_cards_last_four"
        ),
    )
    bank: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    last_four: Mapped[str | None] = mapped_column(String(4))
    statements: Mapped[list["Statement"]] = relationship(viewonly=True, lazy="raise")


class Statement(Identity, CreatedAt, Owned, Base):
    __tablename__ = "statements"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_statements_owner_id"),
        UniqueConstraint(
            "owner_id", "card_id", "id", name="uq_statements_owner_card_id"
        ),
        ForeignKeyConstraint(
            ["owner_id", "card_id"],
            [f"{SCHEMA}.cards.owner_id", f"{SCHEMA}.cards.id"],
            name="fk_statements_card",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "id", "active_import_id"],
            [
                f"{SCHEMA}.imports.owner_id",
                f"{SCHEMA}.imports.statement_id",
                f"{SCHEMA}.imports.id",
            ],
            name="fk_statements_active_import",
            use_alter=True,
            ondelete="RESTRICT",
        ),
    )
    card_id: Mapped[UUID]
    statement_date: Mapped[date | None]
    active_import_id: Mapped[UUID | None]
    imports: Mapped[list["ImportRecord"]] = relationship(
        foreign_keys="[ImportRecord.owner_id, ImportRecord.card_id, ImportRecord.statement_id]",
        viewonly=True,
        lazy="raise",
    )
    active_import: Mapped["ImportRecord | None"] = relationship(
        foreign_keys="[Statement.owner_id, Statement.id, Statement.active_import_id]",
        viewonly=True,
        lazy="raise",
        uselist=False,
    )


class ImportRecord(Identity, CreatedAt, Owned, Base):
    __tablename__ = "imports"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_imports_owner_id"),
        UniqueConstraint(
            "owner_id", "statement_id", "id", name="uq_imports_owner_statement_id"
        ),
        UniqueConstraint(
            "owner_id", "card_id", "file_sha256", name="uq_imports_owner_card_sha256"
        ),
        ForeignKeyConstraint(
            ["owner_id", "card_id"],
            [f"{SCHEMA}.cards.owner_id", f"{SCHEMA}.cards.id"],
            name="fk_imports_card",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "card_id", "statement_id"],
            [
                f"{SCHEMA}.statements.owner_id",
                f"{SCHEMA}.statements.card_id",
                f"{SCHEMA}.statements.id",
            ],
            name="fk_imports_statement",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(file_sha256) = 64", name="ck_imports_sha256_length"),
        CheckConstraint("file_size_bytes >= 0", name="ck_imports_file_size"),
        CheckConstraint("page_count > 0", name="ck_imports_page_count"),
        CheckConstraint("schema_version > 0", name="ck_imports_schema_version"),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'rejected')",
            name="ck_imports_review_status",
        ),
        CheckConstraint(
            "pdf_bytes IS NULL OR length(pdf_bytes) = file_size_bytes",
            name="ck_imports_pdf_size",
        ),
        CheckConstraint(
            "(pdf_bytes IS NOT NULL AND pdf_deleted_at IS NULL) OR "
            "(pdf_bytes IS NULL AND pdf_deleted_at IS NOT NULL)",
            name="ck_imports_pdf_lifecycle",
        ),
    )
    card_id: Mapped[UUID]
    statement_id: Mapped[UUID]
    source_filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Explicit undefer is required; even accidental attribute access cannot fetch the PDF.
    # https://docs.sqlalchemy.org/en/21/orm/queryguide/columns.html#configuring-mapper-level-raiseload-behavior
    pdf_bytes: Mapped[bytes | None] = mapped_column(
        LargeBinary, deferred=True, deferred_raiseload=True
    )
    pdf_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed_statement_date: Mapped[date | None]
    page_count: Mapped[int]
    parser_version: Mapped[str] = mapped_column(Text)
    extractor_version: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    issues: Mapped[list[dict]] = mapped_column(JSON, default=list)
    entries: Mapped[list["Entry"]] = relationship(viewonly=True, lazy="raise")


class Entry(Identity, Owned, Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("import_id", "sequence", name="uq_entries_import_sequence"),
        ForeignKeyConstraint(
            ["owner_id", "import_id"],
            [f"{SCHEMA}.imports.owner_id", f"{SCHEMA}.imports.id"],
            name="fk_entries_import",
            ondelete="RESTRICT",
        ),
        Index("ix_entries_owner_import", "owner_id", "import_id"),
        CheckConstraint("sequence > 0", name="ck_entries_sequence"),
        CheckConstraint("source_page > 0", name="ck_entries_source_page"),
        CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 1000000000000000000)",
            name="ck_entries_amount",
        ),
        CheckConstraint(
            "direction IS NULL OR direction IN ('debit', 'credit')",
            name="ck_entries_direction",
        ),
        CheckConstraint(
            "currency IS NULL OR length(currency) = 3", name="ck_entries_currency"
        ),
        CheckConstraint(
            "entry_type IN ('purchase','payment','refund','cashback','fee','interest','tax','reversal','unknown')",
            name="ck_entries_entry_type",
        ),
    )
    import_id: Mapped[UUID]
    sequence: Mapped[int]
    transaction_date: Mapped[date | None]
    transaction_time: Mapped[time | None]
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    direction: Mapped[str | None] = mapped_column(String(6))
    currency: Mapped[str | None] = mapped_column(String(3))
    entry_type: Mapped[str] = mapped_column(String(16))
    section: Mapped[str] = mapped_column(Text)
    raw_date: Mapped[str] = mapped_column(Text, default="")
    raw_time: Mapped[str] = mapped_column(Text, default="")
    raw_amount: Mapped[str] = mapped_column(Text, default="")
    source_page: Mapped[int]
    source_bbox: Mapped[list[float]] = mapped_column(JSON)
    source_raw_text: Mapped[str] = mapped_column(Text)
    issues: Mapped[list[dict]] = mapped_column(JSON, default=list)

    @validates("amount")
    def validate_amount(self, key, value):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError("Amounts must be Decimal, not float.")
        if (
            not value.is_finite()
            or value < 0
            or value >= Decimal("1000000000000000000")
        ):
            raise ValueError(
                "Amounts must be finite, nonnegative, and fit NUMERIC(20,2)."
            )
        if value.as_tuple().exponent < -2:
            raise ValueError("Amounts must have at most two decimal places.")
        return value
