import tempfile
import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from core.extraction import ParseError
from core.models import Direction, EntryType
from core.parser import parse_pdf
from tests.bank_fixture import BankPage, parse
from tests.hdfc_fixture import pdf_bytes


class YesBankTests(unittest.TestCase):
    def sample(self, **kwargs):
        page = BankPage("yes_bank", **kwargs)
        page.header()
        return page

    def test_repeated_purchases_and_wrapped_rows_across_shifted_pages(self):
        first, second = self.sample(), self.sample(number=2, shift=-1)
        first.row(250, "SYNTHETIC SHOP", "123.45", category="Retail Outlet Services")
        first.row(275, "SYNTHETIC SHOP", "123.45", category="Retail Outlet Services")
        first.footer(310)
        second.row(
            250, "UPI Fuel Surcharge", "2.36", wrapped=True, category="Service Stations"
        )
        second.row(275, "FUEL SURCHARGE WAIVER", "2.00", marker="Cr")
        second.footer(310)
        result = parse(first, second)
        self.assertEqual(result.bank, "yes_bank")
        self.assertEqual(result.parser_version, "yes-bank-0.1.0")
        self.assertEqual(result.statement_date, date(2026, 10, 12))
        self.assertEqual([row.sequence for row in result.transactions], [1, 2, 3, 4])
        self.assertEqual([row.source.page for row in result.transactions], [1, 1, 2, 2])
        self.assertEqual(result.transactions[0].description, "SYNTHETIC SHOP")
        self.assertEqual(result.transactions[1].description, "SYNTHETIC SHOP")
        self.assertIn("Retail Outlet Services", result.transactions[0].source.raw_text)
        self.assertEqual(
            result.transactions[2].description, "UPI Fuel Surcharge SYNTHETIC-REFERENCE"
        )
        self.assertEqual(result.transactions[2].entry_type, EntryType.FEE)
        self.assertEqual(result.transactions[3].entry_type, EntryType.REVERSAL)
        self.assertEqual(
            result.to_dict()["totals"]["INR"], {"debit": "249.26", "credit": "2.00"}
        )
        self.assertFalse(result.needs_review)
        self.assertTrue(
            all(row.transaction_time is None for row in result.transactions)
        )

    def test_payment_interest_tax_fee_and_unknown_credit_are_distinct(self):
        page = self.sample()
        values = [
            ("PAYMENT RECEIVED BBPS - Ref No: SYNTHETIC", "Cr", EntryType.PAYMENT),
            ("FINANCE CHARGES", "Dr", EntryType.INTEREST),
            ("GOODS & SERVICES TAX - GST @ 18%", "Dr", EntryType.TAX),
            ("LATE PAYMENT FEE", "Dr", EntryType.FEE),
            ("SYNTHETIC MERCHANT", "Cr", EntryType.UNKNOWN),
        ]
        for index, (description, marker, _) in enumerate(values):
            page.row(250 + index * 20, description, amount="0.10", marker=marker)
        page.footer(370)
        result = parse(page)
        self.assertEqual(
            [row.entry_type for row in result.transactions], [row[2] for row in values]
        )
        self.assertEqual(result.transactions[0].amount, Decimal("0.10"))
        self.assertTrue(result.needs_review)
        self.assertIn(
            "entry_type_unknown", [i.code for i in result.transactions[-1].issues]
        )

    def test_missing_or_invalid_dates_amounts_and_directions_retain_rows(self):
        cases = [
            {"day": ""},
            {"day": "31/09/2026"},
            {"amount": None},
            {"amount": "bad"},
            {"marker": ""},
            {"marker": "unknown"},
        ]
        for values in cases:
            with self.subTest(values=values):
                page = self.sample()
                page.row(250, **values)
                page.footer(280)
                result = parse(page)
                self.assertEqual(len(result.transactions), 1)
                self.assertTrue(result.needs_review)
                self.assertTrue(result.transactions[0].issues)
                if "day" in values:
                    self.assertIsNone(result.transactions[0].transaction_date)
                if "amount" in values:
                    self.assertIsNone(result.transactions[0].amount)
                if "marker" in values:
                    self.assertIsNone(result.transactions[0].direction)

    def test_empty_description_is_explicitly_flagged(self):
        page = self.sample()
        page.row(250, description="")
        page.footer(280)
        row = parse(page).transactions[0]
        self.assertEqual(row.description, "")
        self.assertIn("description_missing", [i.code for i in row.issues])

    def test_credit_type_with_debit_marker_needs_review(self):
        page = self.sample()
        page.row(250, "PAYMENT RECEIVED BBPS", marker="Dr")
        page.footer(280)
        row = parse(page).transactions[0]
        self.assertEqual(row.entry_type, EntryType.PAYMENT)
        self.assertIn("entry_type_direction_conflict", [i.code for i in row.issues])

    def test_statement_date_missing_or_invalid_preserves_rows(self):
        for value in ("unavailable", "31/09/2026"):
            with self.subTest(value=value):
                page = self.sample()
                page.fragments = [
                    (text.replace("12/10/2026", value), x, top)
                    for text, x, top in page.fragments
                ]
                page.row(250)
                page.footer(280)
                result = parse(page)
                self.assertIsNone(result.statement_date)
                self.assertEqual(len(result.transactions), 1)
                self.assertIn(
                    "statement_date_missing_or_invalid", [i.code for i in result.issues]
                )

    def test_dated_candidate_outside_supported_table_needs_review(self):
        page = self.sample()
        page.row(250)
        page.footer(280)
        page.row(350, "UNSUPPORTED EXTRA TRANSACTION")
        result = parse(page)
        self.assertEqual(len(result.transactions), 1)
        self.assertIn(
            "transaction_outside_supported_table", [i.code for i in result.issues]
        )
        self.assertTrue(result.needs_review)

    def test_unknown_currency_is_not_assumed_to_be_inr(self):
        page = self.sample()
        page.fragments = [
            (text.replace("Amount (Rs.)", "Amount (USD)"), x, top)
            for text, x, top in page.fragments
        ]
        page.row(250)
        page.footer(280)
        result = parse(page)
        self.assertIsNone(result.transactions[0].currency)
        self.assertEqual(result.to_dict()["totals"], {})
        self.assertTrue(result.needs_review)

    def test_missing_table_header_is_rejected(self):
        page = BankPage("yes_bank")
        page.row(250)
        with self.assertRaises(ParseError) as error:
            parse(page)
        self.assertEqual(error.exception.code, "unsupported_layout")

    def test_amount_marker_attached_by_pdf_extraction_is_still_explicit(self):
        page = self.sample()
        page.row(250, amount="12.34Dr", marker="")
        page.footer(280)
        result = parse(page)
        self.assertEqual(result.transactions[0].amount, Decimal("12.34"))
        self.assertEqual(result.transactions[0].direction, Direction.DEBIT)
        self.assertEqual(result.transactions[0].raw_amount, "12.34Dr")
        self.assertFalse(result.needs_review)

    def test_end_of_statement_marker_is_not_part_of_last_description(self):
        page = self.sample()
        page.row(250, "GOODS & SERVICES TAX - GST @ 18%")
        page.add("------------------End of the Statement------------------", 190, 280)
        page.footer(320)
        result = parse(page)
        self.assertEqual(
            result.transactions[0].description, "GOODS & SERVICES TAX - GST @ 18%"
        )
        self.assertNotIn("End of", result.transactions[0].source.raw_text)
        self.assertFalse(result.needs_review)

    def test_encrypted_original_uses_public_dispatch_without_password_leak(self):
        for bank, marker in (("sbi", "C"), ("yes_bank", "Cr")):
            with self.subTest(bank=bank), tempfile.TemporaryDirectory() as directory:
                page = BankPage(bank)
                page.header()
                page.row(250, "PAYMENT RECEIVED BBPS", "42.01", marker=marker)
                page.footer(280)
                plain = Path(directory) / "neutral.pdf"
                plain.write_bytes(pdf_bytes([page]))
                encrypted = Path(directory) / "neutral-encrypted.pdf"
                writer = PdfWriter()
                writer.append(PdfReader(BytesIO(plain.read_bytes())))
                writer.encrypt("invented-bank-password", algorithm="AES-256")
                writer.write(encrypted)
                result = parse_pdf(encrypted, password="invented-bank-password")
                self.assertEqual(result.bank, bank)
                self.assertEqual(result.transactions, parse_pdf(plain).transactions)
                self.assertEqual(result.transactions[0].amount, Decimal("42.01"))
                self.assertNotIn("invented-bank-password", str(result.to_dict()))
                with self.assertRaises(ParseError) as error:
                    parse_pdf(encrypted, password="wrong-invented-password")
                self.assertEqual(error.exception.code, "incorrect_password")
