import unittest
from datetime import date
from decimal import Decimal

from core.extraction import ParseError
from core.models import Direction, EntryType
from tests.bank_fixture import BankPage, parse


class SbiTests(unittest.TestCase):
    def sample(self, **kwargs):
        page = BankPage("sbi", **kwargs)
        page.header()
        return page

    def test_merged_source_cell_becomes_three_entries_without_inheriting_date(self):
        page = self.sample()
        page.row(250, "ANNUAL FEE REVERSAL (EXCL TAX 18.00)", "100.00", marker="C")
        page.row(265, "PAYMENT RECEIVED SYNTHETIC-REFERENCE", "321.09", marker="C")
        page.row(280, "IGST CR @ 18.00%", "18.00", day="", marker="C")
        page.footer(310)
        result = parse(page)
        self.assertEqual(result.bank, "sbi")
        self.assertEqual(result.parser_version, "sbi-0.1.0")
        self.assertEqual(result.statement_date, date(2026, 9, 23))
        self.assertEqual(len(result.transactions), 3)
        self.assertEqual(
            [row.entry_type for row in result.transactions],
            [EntryType.REVERSAL, EntryType.PAYMENT, EntryType.TAX],
        )
        self.assertIsNone(result.transactions[-1].transaction_date)
        self.assertEqual(result.transactions[-1].raw_date, "")
        self.assertIn(
            "date_missing_or_invalid", [i.code for i in result.transactions[-1].issues]
        )
        self.assertEqual(
            result.to_dict()["totals"]["INR"], {"debit": "0.00", "credit": "439.09"}
        )
        self.assertTrue(result.needs_review)

    def test_identical_purchases_are_preserved_and_source_is_located(self):
        first, second = self.sample(), self.sample(number=2, shift=12)
        first.row(250, amount="0.10")
        first.row(270, amount="0.10")
        first.footer(300)
        second.row(250, "FINANCE CHARGES", "0.20", wrapped=True)
        second.footer(300)
        result = parse(first, second)
        self.assertEqual([row.sequence for row in result.transactions], [1, 2, 3])
        self.assertEqual(
            [row.amount for row in result.transactions],
            [Decimal("0.10"), Decimal("0.10"), Decimal("0.20")],
        )
        self.assertEqual(result.transactions[-1].source.page, 2)
        self.assertIn("SYNTHETIC-REFERENCE", result.transactions[-1].description)
        self.assertIn("0.20", result.transactions[-1].source.raw_text)
        self.assertLess(
            result.transactions[-1].source.bbox[0],
            result.transactions[-1].source.bbox[2],
        )
        self.assertEqual(result.to_dict()["totals"]["INR"]["debit"], "0.40")
        self.assertFalse(result.needs_review)
        self.assertTrue(
            all(
                row.transaction_time is None and row.raw_time == ""
                for row in result.transactions
            )
        )

    def test_entry_types_and_unknown_credits_are_conservative(self):
        page = self.sample()
        rows = [
            ("ANNUAL FEE", "D", EntryType.FEE),
            ("FINANCE CHARGES", "D", EntryType.INTEREST),
            ("IGST @ 18%", "D", EntryType.TAX),
            ("SYNTHETIC MERCHANT", "C", EntryType.UNKNOWN),
            ("CASHBACK CREDIT", "C", EntryType.CASHBACK),
            ("REFUND SYNTHETIC MERCHANT", "C", EntryType.REFUND),
        ]
        for index, (description, marker, _) in enumerate(rows):
            page.row(250 + index * 20, description, marker=marker)
        page.footer(390)
        result = parse(page)
        self.assertEqual(
            [row.entry_type for row in result.transactions], [row[2] for row in rows]
        )
        self.assertIn(
            "entry_type_unknown", [i.code for i in result.transactions[3].issues]
        )

    def test_missing_or_invalid_amount_and_direction_are_not_invented(self):
        for amount, marker, expected_amount, expected_direction in [
            (None, "D", None, Direction.DEBIT),
            ("broken", "D", None, Direction.DEBIT),
            ("12,34.50", "D", None, Direction.DEBIT),
            ("12.34", "", Decimal("12.34"), None),
            ("12.34", "X", Decimal("12.34"), None),
            ("-12.34", "D", None, Direction.DEBIT),
        ]:
            with self.subTest(amount=amount, marker=marker):
                page = self.sample()
                page.row(250, amount=amount, marker=marker)
                page.footer(280)
                result = parse(page)
                self.assertEqual(len(result.transactions), 1)
                row = result.transactions[0]
                self.assertEqual(row.amount, expected_amount)
                self.assertEqual(row.direction, expected_direction)
                self.assertTrue(row.issues)
                self.assertTrue(result.needs_review)
                self.assertEqual(result.to_dict()["unresolved_amount_count"], 1)

    def test_invalid_date_is_not_replaced_with_statement_or_previous_date(self):
        page = self.sample()
        page.row(250, day="31 Sep 26")
        page.footer(280)
        row = parse(page).transactions[0]
        self.assertIsNone(row.transaction_date)
        self.assertEqual(row.raw_date, "31 Sep 26")
        self.assertIn("date_missing_or_invalid", [i.code for i in row.issues])

    def test_image_only_or_empty_page_requires_coverage_review(self):
        first = self.sample()
        first.row(250)
        first.footer(280)
        second = BankPage("sbi", number=2)
        second.fragments = []
        result = parse(first, second)
        self.assertEqual(len(result.transactions), 1)
        self.assertIn(
            ("page_without_selectable_text", 2),
            [(i.code, i.page) for i in result.issues],
        )
        self.assertTrue(result.needs_review)

    def test_later_page_without_header_does_not_silently_lose_rows(self):
        for bank in ("sbi", "yes_bank"):
            with self.subTest(bank=bank):
                first = BankPage(bank)
                first.header()
                first.row(250)
                first.footer(280)
                second = BankPage(bank, number=2)
                second.row(250, "UNSUPPORTED EXTRA TRANSACTION")
                result = parse(first, second)
                self.assertEqual(len(result.transactions), 1)
                self.assertIn(
                    ("transaction_outside_supported_table", 2),
                    [(issue.code, issue.page) for issue in result.issues],
                )
                self.assertTrue(result.needs_review)

    def test_table_without_rows_is_not_a_successful_empty_statement(self):
        page = self.sample()
        page.footer(250)
        result = parse(page)
        self.assertEqual(result.transactions, ())
        self.assertIn("empty_transaction_table", [i.code for i in result.issues])

    def test_missing_table_header_is_rejected(self):
        page = BankPage("sbi")
        page.row(250)
        with self.assertRaises(ParseError) as error:
            parse(page)
        self.assertEqual(error.exception.code, "unsupported_layout")

    def test_cardholder_section_caption_is_not_a_purchase_description(self):
        page = self.sample()
        page.row(250, "ANNUAL FEE", "100.00")
        page.add("TRANSACTIONS FOR EXAMPLE HOLDER", 66, 270)
        page.row(290, "SYNTHETIC SHOP (Pay in EMIs)")
        page.footer(320)
        result = parse(page)
        self.assertEqual(len(result.transactions), 2)
        self.assertEqual(
            result.transactions[-1].description, "SYNTHETIC SHOP (Pay in EMIs)"
        )
        self.assertEqual(result.transactions[-1].entry_type, EntryType.PURCHASE)
        self.assertNotIn("EXAMPLE HOLDER", result.transactions[-1].source.raw_text)
        self.assertFalse(result.needs_review)

    def test_missing_statement_date_keeps_rows_for_review(self):
        page = self.sample()
        page.fragments = [
            (text, x, top) for text, x, top in page.fragments if top not in (50, 67)
        ]
        page.row(250)
        page.footer(280)
        result = parse(page)
        self.assertIsNone(result.statement_date)
        self.assertEqual(len(result.transactions), 1)
        self.assertIn(
            "statement_date_missing_or_invalid", [i.code for i in result.issues]
        )
