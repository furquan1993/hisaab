"""Printed bill totals are source evidence, never inferred from spending."""

import unittest
from dataclasses import replace
from decimal import Decimal

from core.parser import parse_pdf_bytes
from core.statement_balance import parse_hdfc_balance
from tests.hdfc_fixture import HdfcPage, pdf_bytes


def bill_page(*, shifted=0, due="C5,216.00"):
    page = HdfcPage()
    for text, x, top in (
        ("PREVIOUS STATEMENT DUES", 25, 100),
        ("PAYMENTS/CREDITS", 145, 96),
        ("PURCHASES/DEBIT", 255, 96),
        ("FINANCE CHARGES", 365, 100),
        ("TOTAL AMOUNT DUE", 480, 100),
        ("RECEIVED", 145, 105),
        ("C4,654.57", 45, 122),
        ("C7,021.41", 155, 122),
        ("C7,582.14", 265, 122),
        ("C0.00", 375, 122),
        (due, 490, 115),
        ("AVAILABLE CREDIT LIMIT C9,99,999.99", 20, 165),
    ):
        page.add(text, x + shifted, top)
    page.header()
    page.row(250, amount="100.00")
    page.footer(280)
    return page


class StatementBalanceTests(unittest.TestCase):
    def test_raised_due_is_not_mistaken_for_previous_balance(self):
        for shift in (0, 12):
            with self.subTest(shift=shift):
                balance = parse_hdfc_balance(bill_page(shifted=shift).page())
                self.assertEqual(balance.amount_due, Decimal("5216.00"))
                self.assertEqual(balance.previous_balance, Decimal("4654.57"))
                self.assertEqual(balance.payments_and_credits, Decimal("7021.41"))
                self.assertEqual(balance.charges, Decimal("7582.14"))
                self.assertEqual(balance.finance_charges, Decimal("0.00"))
                self.assertNotIn("9,99,999", balance.source.raw_text)
                self.assertEqual(balance.source.page, 1)

    def test_pdf_and_serialized_statement_keep_printed_due_separate(self):
        statement = parse_pdf_bytes(pdf_bytes([bill_page()]), source_name="synthetic.pdf")
        data = statement.to_dict()
        self.assertEqual(data["printed_balance"]["amount_due"], "5216.00")
        self.assertEqual(data["totals"]["INR"]["debit"], "100.00")
        self.assertEqual(len(data["transactions"]), 1)

    def test_unknown_ambiguous_or_credit_layouts_are_not_guessed(self):
        self.assertIsNone(parse_hdfc_balance(HdfcPage().page()))
        for due in ("UNREADABLE", "- C5,216.00", "C5,216.00 CR", "C5,,216.00"):
            with self.subTest(due=due):
                self.assertIsNone(parse_hdfc_balance(bill_page(due=due).page()))
        page = bill_page().page()
        duplicate = next(word for word in page.words if word.text == "C5,216.00")
        self.assertIsNone(parse_hdfc_balance(replace(page, words=(*page.words, duplicate))))
