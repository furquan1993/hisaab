"""Immutable contribution receipts and reasoned reconciliation confirmations.

Obligations and balances are derived, never copied into monthly charge records.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKeyConstraint, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, validates

from core.persistence.base import Base, CreatedAt, Identity, Owned


def scope_constraints(name):
    return (
        ForeignKeyConstraint(
            ["owner_id", "card_id"],
            ["hisaab.cards.owner_id", "hisaab.cards.id"],
            ondelete="RESTRICT",
            name=f"fk_{name}_card",
        ),
        ForeignKeyConstraint(
            ["owner_id", "account_id"],
            ["hisaab.accounts.owner_id", "hisaab.accounts.id"],
            ondelete="RESTRICT",
            name=f"fk_{name}_account",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name=f"ck_{name}_currency"),
        CheckConstraint(
            "month = date_trunc('month',month)::date", name=f"ck_{name}_month"
        ),
    )


class Contribution(Identity, CreatedAt, Owned, Base):
    __tablename__ = "contributions"
    __table_args__ = (
        *scope_constraints("contributions"),
        Index(
            "ix_contributions_scope", "owner_id", "card_id", "account_id", "currency"
        ),
        CheckConstraint("amount>0", name="ck_contributions_amount"),
        CheckConstraint(
            "jsonb_typeof(applications::jsonb)='array' AND jsonb_array_length(applications::jsonb)>0",
            name="ck_contributions_applications",
        ),
    )
    card_id: Mapped[UUID]
    account_id: Mapped[UUID]
    currency: Mapped[str] = mapped_column(Text)
    month: Mapped[date]
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    received_on: Mapped[date]
    note: Mapped[str] = mapped_column(Text)
    applications: Mapped[list] = mapped_column(JSON)
    request: Mapped[list] = mapped_column(JSON)
    actor_auth_user_id: Mapped[UUID]

    @validates("amount")
    def validate_amount(self, key, value):
        if not isinstance(value, Decimal):
            raise TypeError("Contribution amounts must be Decimal, not float.")
        if (
            not value.is_finite()
            or value <= 0
            or value >= Decimal(1000000000000000000)
            or value.as_tuple().exponent < -2
        ):
            raise ValueError(
                "Contribution must be a positive exact amount with at most two places."
            )
        return value


class FundingConfirmation(Identity, CreatedAt, Owned, Base):
    __tablename__ = "funding_confirmations"
    __table_args__ = (
        *scope_constraints("funding_confirmations"),
        Index(
            "ix_funding_confirmations_scope",
            "owner_id",
            "card_id",
            "account_id",
            "currency",
            "month",
            "created_at",
        ),
    )
    card_id: Mapped[UUID]
    account_id: Mapped[UUID]
    currency: Mapped[str] = mapped_column(Text)
    month: Mapped[date]
    fingerprint: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    actor_auth_user_id: Mapped[UUID]
