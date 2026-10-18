"""Adapter for the observed YES Bank date/details/category/amount layout."""

import re

from core.bank_table import parse_date, parse_statement
from core.extraction import Page
from core.models import Statement

PARSER_VERSION = "yes-bank-0.1.0"


def parse_pages(
    pages: tuple[Page, ...], *, source_name: str, source_sha256: str, input_kind: str
) -> Statement:
    full_text = "\n".join(page.text for page in pages)
    match = re.search(
        r"Statement Date\s*:\s*(\d{2}/\d{2}/\d{4})", full_text, re.IGNORECASE
    )
    statement_date = parse_date(match[1], ("%d/%m/%Y",)) if match else None
    return parse_statement(
        pages,
        source_name=source_name,
        source_sha256=source_sha256,
        input_kind=input_kind,
        bank="yes_bank",
        version=PARSER_VERSION,
        statement_date=statement_date,
        date_formats=("%d/%m/%Y",),
    )
