"""Opt-in original-PDF checks against private references captured before adapters.

Run with HISAAB_PRIVATE_BANK_TESTS=1. References and credentials are never fixtures
in Git. Failure messages deliberately omit passwords and private transaction data.
"""

import json
import os
import re
import shlex
import unittest
from pathlib import Path

from core.parser import parse_pdf

ROOT = Path(__file__).resolve().parents[1]


def local_passwords():
    """Read only the two expected assignments; never execute the credential file."""
    credentials = {}
    try:
        for line in (ROOT / "credit_card_cred.env").read_text().splitlines():
            match = re.fullmatch(
                r"\s*(?:export\s+)?(SBI_PASS|YESBANK_PASS)\s*=\s*(.*?)\s*", line
            )
            if not match:
                continue
            tokens = shlex.split(match[2], comments=False)
            if len(tokens) != 1:
                raise ValueError
            credentials[match[1]] = tokens[0]
        if set(credentials) != {"SBI_PASS", "YESBANK_PASS"}:
            raise ValueError
    except (OSError, ValueError):
        raise RuntimeError("Cannot load local bank statement credentials.") from None
    return credentials


@unittest.skipUnless(
    os.getenv("HISAAB_PRIVATE_BANK_TESTS") == "1", "private bank validation is opt-in"
)
class PrivateBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.passwords = local_passwords()

    def verify(self, name, bank):
        reference = json.loads(
            (ROOT / "data" / "expected" / "banks" / f"{name}.json").read_text()
        )
        password = self.passwords["SBI_PASS" if bank == "sbi" else "YESBANK_PASS"]
        result = parse_pdf(ROOT / "data" / f"{name}.pdf", password=password)
        data = result.to_dict()
        self.assertEqual(result.bank, bank)
        self.assertEqual(result.source_sha256, reference["source_sha256"])
        self.assertTrue(
            data["statement_date"] == reference["statement_date"],
            "Statement date mismatch",
        )
        self.assertTrue(
            data["totals"] == reference["totals"], "Direction-separated totals mismatch"
        )
        self.assertEqual(len(data["transactions"]), len(reference["transactions"]))
        for index, (actual, expected) in enumerate(
            zip(data["transactions"], reference["transactions"]), start=1
        ):
            self.assertEqual(actual["sequence"], index)
            for key in (
                "transaction_date",
                "description",
                "amount",
                "direction",
                "currency",
                "entry_type",
            ):
                self.assertTrue(
                    actual[key] == expected[key], f"Row {index}: {key} mismatch"
                )
            self.assertEqual(actual["source"]["page"], expected["page"])
            source_words = iter(actual["source"]["raw_text"].split())
            self.assertTrue(
                all(
                    any(word == token for word in source_words)
                    for token in actual["description"].split()
                ),
                f"Row {index}: description missing from provenance",
            )
            self.assertTrue(
                actual["raw_amount"] in actual["source"]["raw_text"],
                f"Row {index}: amount missing from provenance",
            )
        self.assertTrue(password not in json.dumps(data), "Password leaked into output")
        empty_pages = [
            i.page for i in result.issues if i.code == "page_without_selectable_text"
        ]
        self.assertEqual(empty_pages, reference["empty_pages"])
        if empty_pages or any(
            row.transaction_date is None for row in result.transactions
        ):
            self.assertTrue(result.needs_review)

    def test_sbi_original(self):
        self.verify("sbi_card_statement", "sbi")

    def test_sbi_august(self):
        self.verify("sbi_card_statement_aug", "sbi")

    def test_sbi_may(self):
        self.verify("sbi_card_statement_may", "sbi")

    def test_yes_bank_original(self):
        self.verify("yes_bank_statement", "yes_bank")

    def test_yes_bank_july(self):
        self.verify("yes_bank_statement_july", "yes_bank")

    def test_yes_bank_september(self):
        self.verify("yes_bank_statement_sept", "yes_bank")
