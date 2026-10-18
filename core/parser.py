"""Public parsing entry points. Returned facts contain no user decisions."""

import re
from pathlib import Path

from core import hdfc, sbi, yes_bank
from core.extraction import (
    Page,
    ParseError,
    extract_pdf,
    extract_pdf_bytes,
    extract_probe,
)
from core.models import Statement


def _parse_pages(
    pages: tuple[Page, ...], *, source_name: str, source_sha256: str, input_kind: str
) -> Statement:
    text = "\n".join(page.text for page in pages)
    if not text.strip():
        raise ParseError("no_text", "The document has no selectable text.")
    adapters = [
        (r"\bHDFC\s*BANK\b", hdfc.parse_pages),
        (r"\bSBI\s*CARD\b", sbi.parse_pages),
        (r"\bYES\s*BANK\b", yes_bank.parse_pages),
    ]
    matches = [
        adapter
        for pattern, adapter in adapters
        if re.search(pattern, text, re.IGNORECASE)
    ]
    if len(matches) != 1:
        raise ParseError(
            "unsupported_bank", "Statement bank is unsupported or ambiguous."
        )
    return matches[0](
        pages,
        source_name=source_name,
        source_sha256=source_sha256,
        input_kind=input_kind,
    )


def parse_pdf(path: str | Path, *, password: str = "") -> Statement:
    """Parse a supported bank PDF; passwords are used only in memory."""
    path = Path(path)
    pages, digest = extract_pdf(path, password)
    return _parse_pages(
        pages, source_name=path.name, source_sha256=digest, input_kind="pdf"
    )


def parse_pdf_bytes(data: bytes, *, source_name: str, password: str = "") -> Statement:
    """Parse the exact original bytes to be persisted; no filesystem re-read."""
    pages, digest = extract_pdf_bytes(data, password)
    return _parse_pages(
        pages, source_name=source_name, source_sha256=digest, input_kind="pdf"
    )


def parse_probe(path: str | Path) -> Statement:
    """Interpret existing probe JSON for review without reopening the PDF.

    This is diagnostic evidence only. It cannot establish encrypted-PDF
    end-to-end correctness; its digest identifies the probe JSON itself.
    """
    pages, digest, source = extract_probe(Path(path))
    return _parse_pages(
        pages, source_name=source, source_sha256=digest, input_kind="probe"
    )
