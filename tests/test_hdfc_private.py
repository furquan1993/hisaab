"""Optional local-only checks; private references are NEVER committed.

These validate cached extracted text, not fresh decryption of the originals.
A fresh checkout skips them and still runs the synthetic encrypted-PDF tests.
"""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from core.parser import parse_probe

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data/expected/hdfc_rows.json"


@unittest.skipUnless(REFERENCE.exists(), "Private sample references are not present.")
class PrivateHdfcTests(unittest.TestCase):
    def check_sample(self, name):
        sample = json.loads(REFERENCE.read_text())["samples"][name]
        statement = parse_probe(ROOT / sample["probe"])
        result = statement.to_dict()
        self.assertEqual(result["statement_date"], sample["statement_date"])
        # Historical reference totals include repayments; source rows stay intact.
        totals = {currency: dict(values) for currency, values in sample["totals"].items()}
        for row in sample["rows"]:
            if row[6] == "payment":
                totals["INR"][row[4]] = format(
                    Decimal(totals["INR"][row[4]]) - Decimal(row[3]), ".2f"
                )
        self.assertEqual(result["totals"], totals)
        self.assertEqual(result["unresolved_amount_count"], 0)
        self.assertEqual(result["issues"], [])
        self.assertEqual(len(result["transactions"]), len(sample["rows"]))
        for index, (row, expected, description) in enumerate(
            zip(result["transactions"], sample["rows"], sample["descriptions"]), start=1
        ):
            with self.subTest(sample=name, sequence=index):
                self.assertEqual(row["sequence"], index)
                self.assertEqual(
                    [
                        row["transaction_date"],
                        row["transaction_time"],
                        row["amount"],
                        row["direction"],
                        row["source"]["page"],
                        row["entry_type"],
                    ],
                    [
                        expected[0],
                        expected[1],
                        expected[3],
                        expected[4],
                        expected[5],
                        expected[6],
                    ],
                )
                self.assertEqual(row["description"], description)
                self.assertTrue(row["description"].startswith(expected[2]))
                self.assertEqual(row["currency"], "INR")
                self.assertEqual(
                    [issue["code"] for issue in row["issues"]],
                    ["entry_type_unknown"] if expected[6] == "unknown" else [],
                )

    def test_regalia_sample(self):
        self.check_sample("regalia")

    def test_swiggy_sample(self):
        self.check_sample("swiggy")
