import unittest
from dataclasses import replace
from decimal import Decimal

from core.extraction import Page, ParseError
from core.hdfc import parse_pages
from core.models import Direction, EntryType
from tests.hdfc_fixture import HdfcPage


def parse(*builders):
    return parse_pages(
        tuple(b.page() for b in builders),
        source_name="synthetic.pdf",
        source_sha256="a" * 64,
        input_kind="probe",
    )


class HdfcTests(unittest.TestCase):
    def test_rewards_plus_is_not_amount_credit_and_currency_c_is_not_credit(self):
        page = HdfcPage(rewards=True, shifted=True)
        page.header()
        page.row(250, "EXAMPLE HOTEL", "5,432.10", reward=125)
        page.row(270, "EXAMPLE REFUND", "2.00", credit=True)
        page.footer(300)
        result = parse(page)
        self.assertEqual(len(result.transactions), 2)
        debit, credit = result.transactions
        self.assertEqual(
            (debit.amount, debit.direction, debit.currency),
            (Decimal("5432.10"), Direction.DEBIT, "INR"),
        )
        self.assertEqual(debit.description, "EXAMPLE HOTEL")
        self.assertEqual(credit.direction, Direction.CREDIT)
        self.assertEqual(credit.entry_type, EntryType.REFUND)
        self.assertEqual(
            result.to_dict()["totals"]["INR"], {"debit": "5432.10", "credit": "2.00"}
        )

    def test_large_credit_sign_is_not_clipped_by_the_amount_column(self):
        for rewards in (True, False):
            for shifted in (True, False):
                with self.subTest(rewards=rewards, shifted=shifted):
                    page = HdfcPage(rewards=rewards, shifted=shifted)
                    page.header()
                    page.row(250, "EXAMPLE REFUND", "9,99,999.99", credit=True)
                    page.footer(280)
                    row = parse(page).transactions[0]
                    self.assertEqual(row.direction, Direction.CREDIT)
                    self.assertEqual(row.amount, Decimal("999999.99"))

    def test_time_only_row_with_missing_date_and_amount_is_retained(self):
        page = HdfcPage()
        page.header()
        page.row(250, "INCOMPLETE ENTRY", day="", amount=None)
        page.footer(280)
        row = parse(page).transactions[0]
        self.assertIsNone(row.transaction_date)
        self.assertIsNone(row.amount)
        self.assertEqual(row.transaction_time.isoformat(), "12:30:00")

    def test_swiggy_without_rewards_preserves_cashback_payments_and_repeats(self):
        page = HdfcPage(rewards=False)
        page.header()
        page.row(250, "EXAMPLE SHOP", "100.00")
        page.row(270, "EXAMPLE SHOP", "100.00")
        page.row(290, "10% Swiggy CashBack", "10.00", credit=True)
        page.row(310, "CC PAYMENT SYNTHETIC", "200.00", credit=True)
        page.footer(340)
        rows = parse(page).transactions
        self.assertEqual(
            [r.entry_type for r in rows],
            [
                EntryType.PURCHASE,
                EntryType.PURCHASE,
                EntryType.CASHBACK,
                EntryType.PAYMENT,
            ],
        )
        self.assertEqual([r.sequence for r in rows], [1, 2, 3, 4])
        self.assertEqual(rows[0].description, rows[1].description)
        self.assertNotEqual(rows[0].source.bbox, rows[1].source.bbox)

    def test_offsets_repeated_headers_and_international_wrapped_tax(self):
        first = HdfcPage(rewards=True, shifted=True)
        first.header()
        first.row(250)
        first.footer(280)
        second = HdfcPage(rewards=True, number=2)
        second.header()
        second.row(250, "EXAMPLE SHOP TWO", "50.00")
        second.header(top=300, section="International")
        second.row(350, "IGST-SYNTHETIC (Ref#", "6.30", wrapped=True, clock="00:00")
        second.footer(380)
        result = parse(first, second)
        self.assertEqual(len(result.transactions), 3)
        tax = result.transactions[-1]
        self.assertEqual(tax.entry_type, EntryType.TAX)
        self.assertEqual(tax.section, "international")
        self.assertEqual(tax.source.page, 2)
        self.assertEqual(tax.description, "IGST-SYNTHETIC (Ref# SYNTHETIC-REFERENCE)")
        self.assertEqual(tax.amount, Decimal("6.30"))
        self.assertNotIn("EXAMPLE HOLDER", tax.description)
        self.assertEqual(result.statement_date.isoformat(), "2026-10-13")

    def test_missing_and_invalid_fields_are_rows_not_omissions(self):
        page = HdfcPage(rewards=False)
        page.header()
        page.row(250, day="", clock="")
        page.row(270, day="35/10/2026", clock="25:00", amount="broken")
        page.row(290, amount=None)
        page.row(310, currency="")
        page.footer(340)
        result = parse(page)
        self.assertEqual(len(result.transactions), 4)
        self.assertIsNone(result.transactions[0].transaction_date)
        self.assertIsNone(result.transactions[1].transaction_date)
        self.assertIsNone(result.transactions[1].transaction_time)
        self.assertIsNone(result.transactions[1].amount)
        self.assertIsNone(result.transactions[2].amount)
        self.assertIsNone(result.transactions[3].currency)
        self.assertTrue(result.needs_review)

    def test_credit_with_no_description_evidence_is_not_guessed_to_be_refund(self):
        page = HdfcPage()
        page.header()
        page.row(250, "EXAMPLE SHOP", credit=True)
        page.footer(280)
        row = parse(page).transactions[0]
        self.assertEqual(row.entry_type, EntryType.UNKNOWN)
        self.assertIn("entry_type_unknown", [i.code for i in row.issues])

    def test_fees_interest_reversals_and_indian_number_grouping(self):
        page = HdfcPage()
        page.header()
        page.row(250, "1.75% on all DCC Transaction", "1,23,456.78")
        page.row(270, "FINANCE CHARGES", "100.00")
        page.row(290, "SURCHARGE WAIVER", "2.00", credit=True)
        page.footer(320)
        rows = parse(page).transactions
        self.assertEqual(
            [r.entry_type for r in rows],
            [EntryType.FEE, EntryType.INTEREST, EntryType.REVERSAL],
        )
        self.assertEqual(rows[0].amount, Decimal("123456.78"))

    def test_bad_amount_grouping_and_conflicting_markers(self):
        page = HdfcPage()
        page.header()
        page.row(250, amount="1,2.00")
        page.row(270, amount="10.00", credit=True, suffix="DR")
        page.footer(300)
        rows = parse(page).transactions
        self.assertIsNone(rows[0].amount)
        self.assertIsNone(rows[1].direction)

    def test_unsupported_or_incomplete_pages_cannot_look_successful(self):
        with self.assertRaises(ParseError) as error:
            parse_pages(
                (Page(1, "HDFC BANK unrelated terms", ()),),
                source_name="x",
                source_sha256="a",
                input_kind="probe",
            )
        self.assertEqual(error.exception.code, "unsupported_layout")
        page = HdfcPage()
        page.header()
        page.row(250)
        page.footer(280)
        good = page.page()
        result = parse_pages(
            (good, Page(2, "", ())),
            source_name="x",
            source_sha256="a",
            input_kind="probe",
        )
        self.assertIn("page_without_selectable_text", [i.code for i in result.issues])
        self.assertTrue(result.needs_review)
        with self.assertRaises(ParseError) as error:
            parse_pages(
                (replace(good, text="OTHER BANK"),),
                source_name="x",
                source_sha256="a",
                input_kind="probe",
            )
        self.assertEqual(error.exception.code, "unsupported_bank")

    def test_missing_header_is_explicit_when_another_table_is_valid(self):
        page = HdfcPage()
        page.header()
        page.row(250)
        page.add("International Transactions", 25, 300)
        page.row(350, "UNRECOGNIZED TABLE", "2.00")
        page.footer(380)
        result = parse(page)
        self.assertTrue(result.needs_review)
        self.assertIn("unsupported_table_header", [i.code for i in result.issues])

    def test_later_page_without_caption_cannot_silently_lose_transactions(self):
        first = HdfcPage(number=1)
        first.header()
        first.row(250)
        first.footer(280)
        second = HdfcPage(number=2)
        second.row(250, "UNRECOGNIZED CONTINUATION", "10.00")
        result = parse(first, second)
        self.assertTrue(result.needs_review)
        self.assertIn(
            "transaction_outside_supported_table", [i.code for i in result.issues]
        )

    def test_summary_only_table_does_not_mean_successful_empty_statement(self):
        page = HdfcPage()
        page.header()
        page.footer(250)
        result = parse(page)
        self.assertEqual(result.transactions, ())
        self.assertTrue(result.needs_review)
