"""Adapter for observed SBI statements, including merged cells and undated tax.

A row never borrows a preceding transaction's date. Printed two-digit years use
Python's strptime interpretation; no date is synthesized from statement periods.
"""

from datetime import date

from core.bank_table import parse_date, parse_statement
from core.extraction import Page
from core.layout import Line, lines
from core.models import Statement

PARSER_VERSION = "sbi-0.1.0"


def _date_below(header: Line, following: list[Line]) -> date | None:
    label = [
        word for word in header.words if word.text.upper() in ("STATEMENT", "DATE")
    ]
    left, right = (
        min(word.x0 for word in label) - 5,
        max(word.x1 for word in label) + 15,
    )
    for line in following:
        if not 0 < line.top - header.top < 35:
            continue
        raw = " ".join(
            word.text for word in line.words if left <= word.center_x < right
        )
        parsed = parse_date(raw, ("%d %b %Y",))
        if parsed:
            return parsed
    return None


def _statement_date(pages: tuple[Page, ...]) -> date | None:
    if not pages:
        return None
    all_lines = lines(pages[0].words)
    index = next(
        (
            i
            for i, line in enumerate(all_lines)
            if line.text.upper().endswith("STATEMENT DATE")
        ),
        None,
    )
    if index is None:
        return None
    return _date_below(all_lines[index], all_lines[index + 1 :])


def parse_pages(
    pages: tuple[Page, ...], *, source_name: str, source_sha256: str, input_kind: str
) -> Statement:
    return parse_statement(
        pages,
        source_name=source_name,
        source_sha256=source_sha256,
        input_kind=input_kind,
        bank="sbi",
        version=PARSER_VERSION,
        statement_date=_statement_date(pages),
        date_formats=("%d %b %Y", "%d %b %y"),
    )
