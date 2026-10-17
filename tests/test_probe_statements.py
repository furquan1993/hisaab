import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pdfminer.pdfdocument import PDFPasswordIncorrect
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

from scripts.probe_statements import extract_statement, main, save_result


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / "sample.pdf"
        canvas = Canvas(str(self.pdf))
        for y in (720, 700, 680, 660):
            canvas.line(50, y, 450, y)
        for x in (50, 150, 350, 450):
            canvas.line(x, 660, x, 720)
        for y, cells in [(705, ["Date", "Description", "Amount"]),
                         (685, ["01/10/2026", "GROCERY", "123.45"]),
                         (665, ["02/10/2026", "COFFEE", "67.89"])]:
            for x, text in zip((55, 155, 355), cells):
                canvas.drawString(x, y, text)
        canvas.showPage()
        canvas.save()
        self.encrypted = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.append(PdfReader(self.pdf))
        writer.encrypt("synthetic-test-password", algorithm="AES-256")
        writer.write(self.encrypted)

    def test_extract_text_words_and_tables_from_encrypted_pdf(self):
        result = extract_statement(self.encrypted, "synthetic-test-password")
        page = result["pages"][0]
        self.assertIn("GROCERY", page["text"])
        self.assertTrue(page["words"])
        self.assertEqual(page["tables_lines"][0][1],
                         ["01/10/2026", "GROCERY", "123.45"])
        self.assertTrue(page["tables_text"])
        self.assertNotIn("synthetic-test-password", json.dumps(result))
        self.assertNotIn("password", result)

    def test_wrong_password_and_empty_password_rejected(self):
        for password in ("wrong", ""):
            with self.subTest(password=password), self.assertRaises(PDFPasswordIncorrect):
                extract_statement(self.encrypted, password)

    def test_unencrypted_pdf(self):
        self.assertIn("COFFEE", extract_statement(self.pdf, "")["pages"][0]["text"])

    def test_corrupt_pdf(self):
        broken = self.root / "broken.pdf"
        broken.write_bytes(b"not a pdf")
        with self.assertRaises(Exception):
            extract_statement(broken, "")

    def test_private_output_and_no_overwrite(self):
        result = extract_statement(self.pdf, "")
        destination = save_result(result, self.root)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(json.loads(destination.read_text()), result)
        with self.assertRaises(FileExistsError):
            save_result(result, self.root)

    def test_interactive_flow_continues_after_wrong_password(self):
        original_dir = Path.cwd()
        original_umask = os.umask(0o077)
        output = io.StringIO()
        try:
            os.chdir(self.root)
            with patch.object(sys, "argv", ["probe", str(self.encrypted), str(self.pdf)]), \
                 patch("sys.stdin.isatty", return_value=True), \
                 patch("getpass.getpass", side_effect=["wrong", ""]), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = main()
            self.assertEqual(code, 1)
            files = list(Path("data/probes").glob("run-*/*.json"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "sample.json")
            self.assertEqual(stat.S_IMODE(files[0].parent.stat().st_mode), 0o700)
            self.assertIn("incorrect password", output.getvalue())
        finally:
            os.chdir(original_dir)
            os.umask(original_umask)

    def test_noninteractive_invocation_never_reads_password(self):
        script = Path(__file__).resolve().parents[1] / "scripts/probe_statements.py"
        run = subprocess.run([sys.executable, str(script), str(self.encrypted)],
                             input="must-not-be-used", text=True, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("Run in your terminal", run.stderr)
        self.assertNotIn("must-not-be-used", run.stdout + run.stderr)
        self.assertFalse((self.root / "data").exists())


if __name__ == "__main__":
    unittest.main()
