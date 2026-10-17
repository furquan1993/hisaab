"""PDF I/O and validation of the existing local probe format.

pdfplumber 0.11.10: https://github.com/jsvine/pdfplumber/tree/v0.11.10
`extract_words()` returns x0/x1/top/bottom in PDF points, top-left origin.
"""

import json
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from math import isfinite
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException


class ParseError(Exception):
    """Safe error for callers: never contains a dependency's raw exception."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class Page:
    number: int
    text: str
    words: tuple[Word, ...]


def _word(record: dict) -> Word:
    if not isinstance(record["text"], str):
        raise TypeError("Invalid word text")
    coordinates = [float(record[k]) for k in ("x0", "top", "x1", "bottom")]
    if not all(isfinite(v) for v in coordinates):
        raise ValueError("Invalid coordinates")
    if coordinates[2] < coordinates[0] or coordinates[3] < coordinates[1]:
        raise ValueError("Invalid bounding box")
    return Word(record["text"], *coordinates)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise ParseError("input_unreadable", "Cannot read the input file.") from None


def extract_pdf(path: Path, password: str = "") -> tuple[tuple[Page, ...], str]:
    """Open in memory; never write a decrypted PDF."""
    data = _read(path)
    try:
        document = pdfplumber.open(BytesIO(data), password=password)
    except (PDFPasswordIncorrect, PdfminerException) as error:
        underlying = error.args[0] if error.args else None
        if isinstance(error, PDFPasswordIncorrect) or isinstance(
            underlying, PDFPasswordIncorrect
        ):
            raise ParseError(
                "incorrect_password", "A valid PDF password is required."
            ) from None
        raise ParseError("invalid_pdf", "Cannot open this PDF.") from None
    except Exception:
        raise ParseError("invalid_pdf", "Cannot open this PDF.") from None
    try:
        with document:
            pages = tuple(
                Page(
                    i,
                    page.extract_text() or "",
                    tuple(_word(w) for w in page.extract_words()),
                )
                for i, page in enumerate(document.pages, start=1)
            )
    except Exception:
        raise ParseError(
            "extraction_failed", "Cannot extract this PDF safely."
        ) from None
    return pages, sha256(data).hexdigest()


def extract_probe(path: Path) -> tuple[tuple[Page, ...], str, str]:
    """Read diagnostic extraction JSON, not a validated substitute for the PDF.

    The digest identifies this JSON input, NOT the encrypted original PDF.
    """
    data = _read(path)
    try:
        payload = json.loads(data)
        if not isinstance(payload["source"], str) or not payload["source"]:
            raise ValueError("Missing source name")
        if not isinstance(payload["pages"], list) or not payload["pages"]:
            raise ValueError("Missing pages")
        pages = []
        for i, record in enumerate(payload["pages"], start=1):
            if (
                type(record["page"]) is not int
                or record["page"] != i
                or not isinstance(record["text"], str)
                or not isinstance(record["words"], list)
            ):
                raise ValueError("Invalid page")
            pages.append(
                Page(i, record["text"], tuple(_word(w) for w in record["words"]))
            )
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ParseError(
            "invalid_probe", "Expected a complete probe extraction JSON file."
        ) from None
    return tuple(pages), sha256(data).hexdigest(), Path(payload["source"]).name
