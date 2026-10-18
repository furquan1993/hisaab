"""Public parsing entry points. Returned facts contain no user decisions."""

from pathlib import Path

from core.extraction import extract_pdf, extract_probe
from core.hdfc import parse_pages
from core.models import Statement


def parse_pdf(path: str | Path, *, password: str = "") -> Statement:
    """Parse an original HDFC PDF; passwords are used only in memory."""
    path = Path(path)
    pages, digest = extract_pdf(path, password)
    return parse_pages(
        pages, source_name=path.name, source_sha256=digest, input_kind="pdf"
    )


def parse_probe(path: str | Path) -> Statement:
    """Interpret existing probe JSON for review without reopening the PDF.

    This is diagnostic evidence only. It cannot establish encrypted-PDF
    end-to-end correctness; its digest identifies the probe JSON itself.
    """
    pages, digest, source = extract_probe(Path(path))
    return parse_pages(
        pages, source_name=source, source_sha256=digest, input_kind="probe"
    )
