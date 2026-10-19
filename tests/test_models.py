import unittest
from datetime import date, time
from decimal import Decimal

from core.models import Direction, EntryType, Issue, Source, Statement, Transaction


def transaction(**changes):
    fields = dict(
        sequence=1,
        transaction_date=date(2026, 1, 2),
        transaction_time=time(12, 30),
        description="SYNTHETIC SHOP",
        amount=Decimal("123.45"),
        direction=Direction.DEBIT,
        currency="INR",
        entry_type=EntryType.PURCHASE,
        section="domestic",
        raw_date="02/01/2026",
        raw_time="12:30",
        raw_amount="C 123.45",
        source=Source(1, (10, 20, 30, 40), "source"),
    )
    fields.update(changes)
    return Transaction(**fields)


class ModelTests(unittest.TestCase):
    def test_exact_json_values_and_no_decision_fields(self):
        row = transaction()
        result = Statement("sample.pdf", "a" * 64, "pdf", 1, None, (row,)).to_dict()
        data = result["transactions"][0]
        self.assertEqual(data["amount"], "123.45")
        self.assertEqual(data["transaction_date"], "2026-01-02")
        self.assertEqual(data["transaction_time"], "12:30:00")
        self.assertEqual(
            result["totals"], {"INR": {"debit": "123.45", "credit": "0.00"}}
        )
        self.assertEqual(result["status"], "parsed")
        self.assertTrue({"category", "funding_source", "owner"}.isdisjoint(data))

    def test_unknown_fields_and_review_status(self):
        row = transaction(
            amount=None,
            direction=None,
            transaction_date=None,
            issues=(Issue("amount_missing", 1),),
        )
        result = Statement("sample.pdf", "a" * 64, "pdf", 1, None, (row,)).to_dict()
        self.assertIsNone(result["transactions"][0]["amount"])
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["unresolved_amount_count"], 1)

    def test_repeated_purchases_are_not_deduplicated(self):
        rows = (transaction(), transaction(sequence=2))
        self.assertEqual(
            len(Statement("x", "a", "probe", 1, None, rows).to_dict()["transactions"]),
            2,
        )

    def test_amount_validation(self):
        for value in [
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
            Decimal("1.001"),
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                transaction(amount=value)
        with self.assertRaises(TypeError):
            transaction(amount=1.1)

    def test_currency_totals_are_separate(self):
        rows = (
            transaction(),
            transaction(sequence=2, currency="USD", amount=Decimal("2.00")),
        )
        data = Statement("x", "a", "probe", 1, None, rows).to_dict()
        self.assertEqual(data["totals"]["USD"]["debit"], "2.00")
        self.assertEqual(data["totals"]["INR"]["debit"], "123.45")

    def test_payments_are_preserved_but_excluded_from_transaction_totals(self):
        rows = (
            transaction(),
            transaction(
                sequence=2, entry_type=EntryType.PAYMENT,
                direction=Direction.CREDIT, amount=Decimal("500.00"),
            ),
            transaction(
                sequence=3, entry_type=EntryType.REFUND,
                direction=Direction.CREDIT, amount=Decimal("10.25"),
            ),
            transaction(
                sequence=4, entry_type=EntryType.CASHBACK,
                direction=Direction.CREDIT, amount=Decimal("2.10"),
            ),
            transaction(
                sequence=5, entry_type=EntryType.PAYMENT,
                direction=Direction.DEBIT, amount=Decimal("50.00"),
            ),
            transaction(
                sequence=6, entry_type=EntryType.PAYMENT,
                direction=Direction.CREDIT, currency="USD",
            ),
        )
        data = Statement("x", "a", "probe", 1, None, rows).to_dict()
        self.assertEqual(
            data["totals"],
            {
                "INR": {"debit": "123.45", "credit": "12.35"},
                "USD": {"debit": "0.00", "credit": "0.00"},
            },
        )
        self.assertEqual(len(data["transactions"]), len(rows))
        self.assertEqual(data["transactions"][1]["amount"], "500.00")
        self.assertEqual(data["transactions"][1]["entry_type"], "payment")
