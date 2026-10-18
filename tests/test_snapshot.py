import unittest
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from core.extraction import ParseError
from core.parser import parse_pdf_bytes
from tests.hdfc_fixture import HdfcPage, pdf_bytes


def statement_bytes(description="SYNTHETIC SHOP"):
    page = HdfcPage()
    page.header()
    page.row(250, description, "123.45")
    page.row(270, description, "123.45")
    page.footer(300)
    return pdf_bytes([page])


def encrypt(data):
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(data)))
    writer.encrypt("synthetic-password", algorithm="AES-256")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class SnapshotTests(unittest.TestCase):
    def test_bytes_preserve_source_fingerprint_and_identical_rows(self):
        data = statement_bytes()
        result = parse_pdf_bytes(data, source_name="renamed.file")
        self.assertEqual(result.source_sha256, sha256(data).hexdigest())
        self.assertEqual(result.source_name, "renamed.file")
        self.assertEqual(len(result.transactions), 2)
        self.assertEqual(
            result.transactions[0].description, result.transactions[1].description
        )

    def test_encrypted_snapshot_and_wrong_password(self):
        data = encrypt(statement_bytes())
        with self.assertRaises(ParseError):
            parse_pdf_bytes(data, source_name="test.pdf")
        result = parse_pdf_bytes(
            data, source_name="test.pdf", password="synthetic-password"
        )
        self.assertEqual(result.source_sha256, sha256(data).hexdigest())

    def test_json_is_not_accepted_as_pdf(self):
        with self.assertRaises(ParseError) as error:
            parse_pdf_bytes(
                b'{"source":"synthetic.pdf","pages":[]}', source_name="test.pdf"
            )
        self.assertEqual(error.exception.code, "invalid_pdf")
