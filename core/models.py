"""Versioned parsing contract: source facts, never user decisions.

Amounts are nonnegative Decimal values; direction carries their financial sign.
JSON serializes decimals as strings and dates/times using ISO 8601.
Source positions use PDF points measured from the page's top-left corner.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, time
from decimal import Decimal
from enum import StrEnum

PARSER_VERSION = "hdfc-0.1.0"


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class EntryType(StrEnum):
    PURCHASE = "purchase"
    PAYMENT = "payment"
    REFUND = "refund"
    CASHBACK = "cashback"
    FEE = "fee"
    INTEREST = "interest"
    TAX = "tax"
    REVERSAL = "reversal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Issue:
    code: str
    page: int | None = None


@dataclass(frozen=True)
class Source:
    page: int
    bbox: tuple[float, float, float, float]
    raw_text: str


@dataclass(frozen=True)
class Transaction:
    sequence: int
    transaction_date: date | None
    transaction_time: time | None
    description: str
    amount: Decimal | None
    direction: Direction | None
    currency: str | None
    entry_type: EntryType
    section: str
    raw_date: str
    raw_time: str
    raw_amount: str
    source: Source
    issues: tuple[Issue, ...] = ()

    def __post_init__(self):
        if self.amount is not None:
            if not isinstance(self.amount, Decimal):
                raise TypeError("Amounts must be Decimal, not float.")
            if not self.amount.is_finite() or self.amount < 0:
                raise ValueError("Amounts must be finite and nonnegative.")
            if self.amount.as_tuple().exponent < -2:
                raise ValueError(
                    "Statement amounts must have at most two decimal places."
                )


@dataclass(frozen=True)
class Statement:
    source_name: str
    source_sha256: str
    input_kind: str
    page_count: int
    statement_date: date | None
    transactions: tuple[Transaction, ...]
    issues: tuple[Issue, ...] = ()
    bank: str = "hdfc"
    parser_version: str = PARSER_VERSION
    schema_version: int = 1

    @property
    def needs_review(self) -> bool:
        return bool(self.issues or any(row.issues for row in self.transactions))

    def to_dict(self) -> dict:
        def encode(value):
            if isinstance(value, Decimal):
                return format(value, ".2f")
            if isinstance(value, (date, time)):
                return value.isoformat()
            raise TypeError(f"Unsupported serialization type: {type(value).__name__}")

        data = json.loads(json.dumps(asdict(self), default=encode))
        data["status"] = "needs_review" if self.needs_review else "parsed"
        # Totals include only rows with a known amount AND direction, and never
        # pretend a multi-currency sum has financial meaning.
        currencies = sorted({r.currency for r in self.transactions if r.currency})
        data["totals"] = {
            currency: {
                direction.value: format(
                    sum(
                        (
                            r.amount
                            for r in self.transactions
                            if r.currency == currency
                            and r.direction == direction
                            and r.amount is not None
                        ),
                        Decimal("0"),
                    ),
                    ".2f",
                )
                for direction in Direction
            }
            for currency in currencies
        }
        data["unresolved_amount_count"] = sum(
            r.amount is None or r.direction is None or r.currency is None
            for r in self.transactions
        )
        return data
