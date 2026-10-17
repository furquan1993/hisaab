import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
from itertools import permutations
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from core.cli import main
from core.extraction import ParseError
from core.output import save_statement
from core.parser import parse_pdf, parse_probe
from tests.hdfc_fixture import HdfcPage, pdf_bytes


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pages = []
        for number, rewards in [(1, True), (2, False)]:
            page = HdfcPage(rewards=rewards, shifted=(number == 1), number=number)
            page.header()
            page.row(250, "SYNTHETIC SHOP", "123.45", reward=50 if rewards else None)
            page.row(270, "EXAMPLE REFUND", "12.00", credit=True)
            page.footer(300)
            self.pages.append(page)
        self.pdf = self.root / "synthetic.pdf"
        self.pdf.write_bytes(pdf_bytes(self.pages))
        self.encrypted = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.append(PdfReader(BytesIO(self.pdf.read_bytes())))
        writer.encrypt("synthetic-password", algorithm="AES-256")
        writer.write(self.encrypted)
        self.probe = self.root / "synthetic.json"
        self.probe.write_text(
            json.dumps(
                {
                    "source": "synthetic.pdf",
                    "pages": [p.probe_record() for p in self.pages],
                }
            )
        )

    def invoke(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            code = main(list(args) + ["--output-dir", str(self.root / "results")])
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_pdf_and_encrypted_pdf_produce_same_rows(self):
        plain = parse_pdf(self.pdf)
        encrypted = parse_pdf(self.encrypted, password="synthetic-password")
        self.assertEqual(plain.transactions, encrypted.transactions)
        self.assertEqual(len(encrypted.transactions), 4)
        self.assertEqual(
            encrypted.to_dict()["totals"]["INR"], {"debit": "246.90", "credit": "24.00"}
        )
        self.assertEqual(encrypted.input_kind, "pdf")
        self.assertEqual(
            encrypted.source_sha256, sha256(self.encrypted.read_bytes()).hexdigest()
        )
        self.assertNotIn("synthetic-password", json.dumps(encrypted.to_dict()))

    def test_probe_provenance_is_not_claimed_as_pdf_hash(self):
        result = parse_probe(self.probe)
        self.assertEqual(len(result.transactions), 4)
        self.assertEqual(result.input_kind, "probe")
        self.assertEqual(
            result.source_sha256, sha256(self.probe.read_bytes()).hexdigest()
        )
        self.assertNotEqual(
            result.source_sha256, sha256(self.pdf.read_bytes()).hexdigest()
        )

    def test_wrong_password_and_corrupt_pdf_are_safe_errors(self):
        with self.assertRaises(ParseError) as error:
            parse_pdf(self.encrypted, password="wrong-secret")
        self.assertEqual(error.exception.code, "incorrect_password")
        broken = self.root / "broken.pdf"
        broken.write_bytes(b"private content not a PDF")
        with self.assertRaises(ParseError) as error:
            parse_pdf(broken)
        self.assertNotIn("private content", str(error.exception))
        self.assertEqual(error.exception.code, "invalid_pdf")

    def test_probe_validates_shape_page_order_and_coordinates(self):
        original = json.loads(self.probe.read_text())
        bad = [None, {}, {"source": "x", "pages": []}]
        wrong_page = json.loads(json.dumps(original))
        wrong_page["pages"][0]["page"] = 9
        bad.append(wrong_page)
        bad_coordinates = json.loads(json.dumps(original))
        bad_coordinates["pages"][0]["words"][0]["x0"] = float("inf")
        bad.append(bad_coordinates)
        for payload in bad:
            self.probe.write_text(json.dumps(payload))
            with (
                self.subTest(payload_type=type(payload).__name__),
                self.assertRaises(ParseError) as error,
            ):
                parse_probe(self.probe)
            self.assertEqual(error.exception.code, "invalid_probe")

    def test_private_output_never_overwrites_and_keeps_source(self):
        result = parse_probe(self.probe)
        first = save_statement(result, self.root / "outputs")
        second = save_statement(result, self.root / "outputs")
        self.assertNotEqual(first, second)
        self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(first.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads(first.read_text()), result.to_dict())

    def test_cli_summary_hides_transactions_until_explicitly_requested(self):
        code, output = self.invoke("parse-probe", str(self.probe))
        self.assertEqual(code, 0)
        self.assertEqual(output[0]["transaction_count"], 4)
        self.assertEqual(output[0]["source"], self.probe.name)
        self.assertNotIn("SYNTHETIC SHOP", json.dumps(output))
        self.assertTrue(Path(output[0]["output"]).is_file())
        code, output = self.invoke(
            "parse-probe", str(self.probe), "--show-transactions"
        )
        self.assertEqual(code, 0)
        self.assertEqual(output[0]["transactions"][0]["description"], "SYNTHETIC SHOP")

    def test_cli_noninteractive_password_requirement_is_explicit(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            patch("getpass.getpass") as prompt,
        ):
            code, output = self.invoke("parse", str(self.encrypted))
        self.assertEqual(code, 1)
        self.assertEqual(output[0]["error"]["code"], "password_required")
        prompt.assert_not_called()
        self.assertFalse((self.root / "results").exists())

    def test_cli_hidden_password_prompt(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("getpass.getpass", return_value="synthetic-password"),
        ):
            code, output = self.invoke("parse", str(self.encrypted))
        self.assertEqual(code, 0)
        self.assertNotIn("synthetic-password", json.dumps(output))

    def test_cli_review_exit_code_and_no_silent_failure(self):
        payload = json.loads(self.probe.read_text())
        payload["pages"].append({"page": 3, "text": "", "words": []})
        self.probe.write_text(json.dumps(payload))
        code, output = self.invoke("parse-probe", str(self.probe))
        self.assertEqual(code, 3)
        self.assertEqual(output[0]["status"], "needs_review")

    def test_cli_continues_after_one_input_fails(self):
        code, output = self.invoke(
            "parse-probe", str(self.root / "missing.json"), str(self.probe)
        )
        self.assertEqual(code, 1)
        self.assertEqual(len(output), 2)
        self.assertEqual(output[0]["error"]["code"], "input_unreadable")
        self.assertEqual(output[1]["transaction_count"], 4)

    def test_cli_failure_outranks_review_and_success_in_every_order(self):
        payload = json.loads(self.probe.read_text())
        payload["pages"].append({"page": 3, "text": "", "words": []})
        review = self.root / "needs-review.json"
        review.write_text(json.dumps(payload))
        missing = self.root / "missing.json"
        for inputs in permutations((missing, review, self.probe)):
            with self.subTest(order=[path.name for path in inputs]):
                code, output = self.invoke("parse-probe", *map(str, inputs))
                self.assertEqual(code, 1)
                self.assertEqual(len(output), 3)

    def test_cli_review_outranks_success_in_either_order(self):
        payload = json.loads(self.probe.read_text())
        payload["pages"].append({"page": 3, "text": "", "words": []})
        review = self.root / "needs-review.json"
        review.write_text(json.dumps(payload))
        for inputs in permutations((review, self.probe)):
            with self.subTest(order=[path.name for path in inputs]):
                code, output = self.invoke("parse-probe", *map(str, inputs))
                self.assertEqual(code, 3)
                self.assertEqual(len(output), 2)

    def test_cli_cancellation_stops_batch_and_keeps_prior_results(self):
        statement = parse_probe(self.probe)
        for error in (KeyboardInterrupt(), EOFError()):
            with (
                self.subTest(error=type(error).__name__),
                patch("core.cli.parse_probe", side_effect=[statement, error]) as parser,
            ):
                code, output = self.invoke("parse-probe", *([str(self.probe)] * 3))
                self.assertEqual(code, 130)
                self.assertEqual(parser.call_count, 2)
                self.assertEqual(len(output), 2)
                self.assertTrue(Path(output[0]["output"]).is_file())
                self.assertEqual(output[1]["error"]["code"], "cancelled")

    def test_cli_output_failure_does_not_leak_raw_errors(self):
        with patch("core.cli.save_statement", side_effect=OSError("private-content")):
            code, output = self.invoke("parse-probe", str(self.probe))
        self.assertEqual(code, 1)
        self.assertEqual(output[0]["error"]["code"], "output_failed")
        self.assertNotIn("private-content", json.dumps(output))

    def test_cli_unexpected_failure_does_not_leak_raw_errors(self):
        with patch("core.cli.parse_probe", side_effect=RuntimeError("private-content")):
            code, output = self.invoke("parse-probe", str(self.probe))
        self.assertEqual(code, 1)
        self.assertEqual(output[0]["error"]["code"], "internal_error")
        self.assertNotIn("private-content", json.dumps(output))

    def test_cli_rejects_unknown_arguments_without_echoing_secrets(self):
        output = StringIO()
        with redirect_stdout(output):
            code = main(["parse", str(self.pdf), "--password", "secret-value"])
        self.assertEqual(code, 2)
        self.assertNotIn("secret-value", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "usage_error")
