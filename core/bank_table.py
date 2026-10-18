"""Positioned rows shared by the observed SBI and YES Bank layouts.

These banks print dates without times and explicit C/D or Cr/Dr amount markers.
This is intentionally separate from HDFC's amount-sign/rewards interpretation.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from core.extraction import Page, ParseError, Word
from core.layout import Line, lines
from core.models import Direction, EntryType, Issue, Source, Statement, Transaction

NUMBER = re.compile(r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})\.\d{2}")
DATE = re.compile(
    r"(?:\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[a-z]{3}\s+\d{2,4})", re.IGNORECASE
)
MARKERS = {
    "C": Direction.CREDIT,
    "CR": Direction.CREDIT,
    "D": Direction.DEBIT,
    "DR": Direction.DEBIT,
}


@dataclass(frozen=True)
class Table:
    page: int
    date_left: float
    description_left: float
    description_right: float
    amount_left: float
    amount_right: float
    currency: str | None
    body: tuple[Word, ...]


def _header(line: Line) -> bool:
    return {"DATE", "TRANSACTION", "DETAILS", "AMOUNT"} <= {
        w.text.upper() for w in line.words
    }


def _footer(line: Line) -> bool:
    return (
        line.text.lower()
        .strip("- ")
        .startswith(
            (
                "end of the statement",
                "transactions highlighted",
                "c=credit",
                "important messages",
                "important information",
                "*total amount due",
                'sms "help"',
                "yes touch",
                "rewards summary",
                "page ",
            )
        )
    )


def _metadata(line: Line) -> bool:
    return line.text.lower().startswith(
        ("for statement period:", "transactions for ")
    ) and not any(NUMBER.fullmatch(word.text) for word in line.words)


def _table(page: Page, header: Line, following: list[Line], bank: str) -> Table | None:
    headings = {w.text.upper(): w for w in header.words}
    date_heading, amount = headings["DATE"], headings["AMOUNT"]
    if bank == "sbi":
        date_left = date_heading.x0 - 20
        description_left = date_heading.x1 + 10
        description_right = amount.x0 - 45
        amount_left = description_right
    else:
        if not {"MERCHANT", "CATEGORY"} <= headings.keys():
            return None
        date_left = date_heading.x0 - 5
        description_left = headings["TRANSACTION"].x0 - 2
        description_right = headings["MERCHANT"].x0 - 2
        amount_left = (headings["CATEGORY"].x1 + amount.x0) / 2
    amount_right = amount.x1 + 35
    if (
        not date_left
        < description_left
        < description_right
        <= amount_left
        < amount_right
    ):
        return None
    start = max(w.bottom for w in header.words)
    end = next(
        (line.top for line in following if _footer(line) or _header(line)), float("inf")
    )
    body = tuple(
        w
        for line in following
        if start < line.top < end and not _metadata(line)
        for w in line.words
        if date_left <= w.center_x < amount_right
    )
    currency = (
        "INR" if re.search(r"(?:\bRs\b|INR|`|₹)", header.text, re.IGNORECASE) else None
    )
    return Table(
        page.number,
        date_left,
        description_left,
        description_right,
        amount_left,
        amount_right,
        currency,
        body,
    )


def _tables(page: Page, bank: str) -> tuple[list[Table], list[Issue]]:
    found, issues = [], []
    all_lines = lines(page.words)
    for index, line in enumerate(all_lines):
        if not _header(line):
            continue
        table = _table(page, line, all_lines[index + 1 :], bank)
        if table is None:
            issues.append(Issue("unsupported_table_header", page.number))
        else:
            found.append(table)
    return found, issues


def _date_text(line: Line, table: Table) -> str:
    return " ".join(
        w.text
        for w in line.words
        if table.date_left <= w.center_x < table.description_left
    )


def _anchor(line: Line, table: Table) -> bool:
    return bool(_date_text(line, table)) or any(
        table.amount_left <= w.center_x < table.amount_right for w in line.words
    )


def _groups(table: Table) -> list[list[Line]]:
    body = lines(table.body)
    anchors = [line.top for line in body if _anchor(line, table)]
    grouped = []
    for index, anchor in enumerate(anchors):
        low = (anchors[index - 1] + anchor) / 2 if index else float("-inf")
        high = (
            (anchor + anchors[index + 1]) / 2
            if index + 1 < len(anchors)
            else float("inf")
        )
        grouped.append([line for line in body if low <= line.top < high])
    return grouped


def parse_date(raw: str, formats: tuple[str, ...]) -> date | None:
    for format_ in formats:
        try:
            return datetime.strptime(raw, format_).date()
        except ValueError:
            continue
    return None


def _amount(
    raw: str, page: int
) -> tuple[Decimal | None, Direction | None, list[Issue]]:
    # Some PDFs position the suffix close enough to merge it into the number.
    normalized = re.sub(r"(?<=\d)(?=(?:Cr|Dr|C|D)$)", " ", raw, flags=re.IGNORECASE)
    parts = normalized.split()
    issues = []
    amount = None
    direction = None
    if parts and NUMBER.fullmatch(parts[0]) and len(parts) <= 2:
        amount = Decimal(parts[0].replace(",", ""))
    if parts and len(parts) <= 2:
        direction = MARKERS.get(parts[-1].upper())
    if amount is None:
        issues.append(Issue("amount_missing_or_invalid", page))
    if direction is None:
        issues.append(Issue("direction_missing_or_unknown", page))
    return amount, direction, issues


def _entry_type(description: str, direction: Direction | None) -> EntryType:
    text = description.upper()
    if "REVERS" in text or "WAIVER" in text:
        return EntryType.REVERSAL
    if "PAYMENT RECEIVED" in text:
        return EntryType.PAYMENT
    if "REFUND" in text:
        return EntryType.REFUND
    if "CASHBACK" in text:
        return EntryType.CASHBACK
    if re.search(r"\b(?:[ICS]?GST|SERVICE TAX|GOODS & SERVICES TAX)\b", text):
        return EntryType.TAX
    if "FINANCE CHARG" in text or "INTEREST CHARG" in text:
        return EntryType.INTEREST
    if "FEE" in text or "SURCHARGE" in text:
        return EntryType.FEE
    return EntryType.PURCHASE if direction == Direction.DEBIT else EntryType.UNKNOWN


def _row_issues(
    description: str,
    kind: EntryType,
    direction: Direction | None,
    currency: str | None,
    page: int,
) -> list[Issue]:
    issues = []
    if currency is None:
        issues.append(Issue("currency_missing_or_unknown", page))
    if not description:
        issues.append(Issue("description_missing", page))
    if kind == EntryType.UNKNOWN:
        issues.append(Issue("entry_type_unknown", page))
    if (
        kind
        in (EntryType.PAYMENT, EntryType.REFUND, EntryType.CASHBACK, EntryType.REVERSAL)
        and direction != Direction.CREDIT
    ):
        issues.append(Issue("entry_type_direction_conflict", page))
    return issues


def _transaction(
    table: Table, selected: list[Line], sequence: int, formats: tuple[str, ...]
) -> Transaction:
    words = tuple(w for line in selected for w in line.words)
    raw_date = " ".join(_date_text(line, table) for line in selected).strip()
    parsed_date = parse_date(raw_date, formats)
    issues = [] if parsed_date else [Issue("date_missing_or_invalid", table.page)]
    description = " ".join(
        w.text
        for line in selected
        for w in line.words
        if table.description_left <= w.center_x < table.description_right
    )
    raw_amount = " ".join(
        w.text for w in words if table.amount_left <= w.center_x < table.amount_right
    )
    amount, direction, amount_issues = _amount(raw_amount, table.page)
    issues.extend(amount_issues)
    kind = _entry_type(description, direction)
    issues.extend(_row_issues(description, kind, direction, table.currency, table.page))
    bbox = (
        min(w.x0 for w in words),
        min(w.top for w in words),
        max(w.x1 for w in words),
        max(w.bottom for w in words),
    )
    source = Source(
        table.page,
        tuple(round(value, 3) for value in bbox),
        "\n".join(line.text for line in selected),
    )
    return Transaction(
        sequence=sequence,
        transaction_date=parsed_date,
        transaction_time=None,
        description=description,
        amount=amount,
        direction=direction,
        currency=table.currency,
        entry_type=kind,
        section="transactions",
        raw_date=raw_date,
        raw_time="",
        raw_amount=raw_amount,
        source=source,
        issues=tuple(issues),
    )


def _coverage_issues(page: Page, found: list[Table]) -> list[Issue]:
    covered = {word for table in found for word in table.body}
    issues = []
    for line in lines(page.words):
        if all(word in covered for word in line.words):
            continue
        # Detect headerless continuation pages without assuming old coordinates.
        dated_amount = DATE.match(line.text) and re.search(
            r"\d[\d,]*\.\d{2}\s*(?:Cr|Dr|C|D)\s*$", line.text, re.IGNORECASE
        )
        if dated_amount or any(
            DATE.fullmatch(_date_text(line, table))
            and any(
                table.amount_left <= w.center_x < table.amount_right for w in line.words
            )
            for table in found
        ):
            issues.append(Issue("transaction_outside_supported_table", page.number))
    return issues


def _parse_page(
    page: Page, bank: str, sequence: int, formats: tuple[str, ...]
) -> tuple[list[Transaction], list[Issue], int]:
    found, issues = _tables(page, bank)
    if not page.text.strip() or not page.words:
        issues.append(Issue("page_without_selectable_text", page.number))
    issues.extend(_coverage_issues(page, found))
    transactions = []
    for table in found:
        grouped = _groups(table)
        if not grouped:
            issues.append(Issue("empty_transaction_table", page.number))
            if table.body:
                issues.append(Issue("unanchored_transaction_text", page.number))
        start_sequence = sequence + len(transactions)
        transactions.extend(
            _transaction(table, group, start_sequence + index, formats)
            for index, group in enumerate(grouped)
        )
    return transactions, issues, len(found)


def parse_statement(
    pages: tuple[Page, ...],
    *,
    source_name: str,
    source_sha256: str,
    input_kind: str,
    bank: str,
    version: str,
    statement_date: date | None,
    date_formats: tuple[str, ...],
) -> Statement:
    if not any(page.text.strip() for page in pages):
        raise ParseError("no_text", "The document has no selectable text.")
    transactions, issues = [], []
    if statement_date is None:
        issues.append(Issue("statement_date_missing_or_invalid"))
    table_count = 0
    for page in pages:
        rows, page_issues, count = _parse_page(
            page, bank, len(transactions) + 1, date_formats
        )
        transactions.extend(rows)
        issues.extend(page_issues)
        table_count += count
    if not table_count:
        raise ParseError("unsupported_layout", "No supported transaction table found.")
    return Statement(
        source_name=source_name,
        source_sha256=source_sha256,
        input_kind=input_kind,
        page_count=len(pages),
        statement_date=statement_date,
        transactions=tuple(transactions),
        issues=tuple(issues),
        bank=bank,
        parser_version=version,
    )
