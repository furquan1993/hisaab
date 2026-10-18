"""Parser for the two observed HDFC statement variants.

In these layouts '+' in the AMOUNT column means credit; '+' in REWARDS
must not affect direction. The extracted 'C' glyph is HDFC's rupee symbol,
not a credit marker. The printed EMI badge is retained in the description;
it is NOT treated as evidence of an installment payment.
"""

import re
from collections.abc import Iterator
from datetime import date, datetime, time
from decimal import Decimal

from core.extraction import Page, ParseError
from core.layout import Line, Table, lines, tables
from core.models import Direction, EntryType, Issue, Source, Statement, Transaction

DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
TIME = re.compile(r"\d{2}:\d{2}")
NUMBER = r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})\.\d{2}"
MONEY = re.compile(
    rf"(?P<sign>[+-])?\s*(?P<currency>INR|Rs\.?|C|₹|USD|EUR|GBP|\$)?"
    rf"\s*(?P<amount>{NUMBER})\s*(?P<direction>CR|DR)?",
    re.IGNORECASE,
)


def _amount(raw: str, page: int):
    match = MONEY.fullmatch(raw.strip())
    if not match:
        return None, None, None, [Issue("amount_unreadable", page)]
    issues = []
    marker = (match["currency"] or "").upper()
    currency = "INR" if marker in ("C", "₹", "INR", "RS", "RS.") else marker or None
    if currency == "$":
        currency = None  # A dollar glyph alone does not identify a currency.
    if currency is None:
        issues.append(Issue("currency_unknown", page))
    sign, suffix = match["sign"], (match["direction"] or "").upper()
    direction = Direction.CREDIT if sign == "+" or suffix == "CR" else Direction.DEBIT
    if sign == "-" or (sign == "+" and suffix == "DR"):
        direction = None
        issues.append(Issue("direction_ambiguous", page))
    return Decimal(match["amount"].replace(",", "")), direction, currency, issues


def _entry_type(description: str, direction: Direction | None) -> EntryType:
    text = description.upper()
    if re.search(
        r"\b(AUTOPAY THANK YOU|CC PAYMENT|PAYMENT RECEIVED|PAYMENT THANK YOU)\b", text
    ):
        return EntryType.PAYMENT
    if "CASHBACK" in text or "CASH BACK" in text:
        return EntryType.CASHBACK
    if "REVERSAL" in text or "WAIVER" in text:
        return EntryType.REVERSAL
    if "REFUND" in text or "RETURN" in text:
        return EntryType.REFUND
    if re.match(r"^(IGST|CGST|SGST)\b", text) or text.startswith(
        ("IGST-", "CGST-", "SGST-")
    ):
        return EntryType.TAX
    if "INTEREST" in text or "FINANCE CHARGE" in text:
        return EntryType.INTEREST
    if re.search(r"\b(FEE|FEES|SURCHARGE|DCC TRANSACTION)\b", text):
        return EntryType.FEE
    return EntryType.PURCHASE if direction == Direction.DEBIT else EntryType.UNKNOWN


def _is_row_anchor(line: Line, table: Table) -> bool:
    # Keep an amount without a date, and a date/time without an amount.
    return any(
        table.amount_left <= w.center_x < table.amount_right for w in line.words
    ) or any(
        w.center_x < table.description_left
        and (DATE.search(w.text) or TIME.fullmatch(w.text))
        for w in line.words
    )


def _row_groups(table: Table) -> Iterator[list[Line]]:
    """Associate continuations with the nearest row's date/amount baseline."""
    body_lines = lines(table.body)
    anchors = [line.top for line in body_lines if _is_row_anchor(line, table)]
    for index, anchor in enumerate(anchors):
        low = (anchors[index - 1] + anchor) / 2 if index else float("-inf")
        high = (
            (anchor + anchors[index + 1]) / 2
            if index + 1 < len(anchors)
            else float("inf")
        )
        yield [line for line in body_lines if low <= line.top < high]


def _date_time(
    raw_date: str, raw_time: str, page: int
) -> tuple[date | None, time | None, list[Issue]]:
    issues = []
    try:
        parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
    except ValueError:
        parsed_date = None
        issues.append(Issue("date_missing_or_invalid", page))
    try:
        parsed_time = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        parsed_time = None
        issues.append(Issue("time_missing_or_invalid", page))
    return parsed_date, parsed_time, issues


def _row_issues(
    description: str, kind: EntryType, direction: Direction | None, page: int
) -> list[Issue]:
    issues = []
    if not description:
        issues.append(Issue("description_missing", page))
    if kind == EntryType.UNKNOWN:
        issues.append(Issue("entry_type_unknown", page))
    if (
        kind in (EntryType.PAYMENT, EntryType.CASHBACK)
        and direction != Direction.CREDIT
    ):
        issues.append(Issue("entry_type_direction_conflict", page))
    return issues


def _transaction(table: Table, selected: list[Line], sequence: int) -> Transaction:
    words = tuple(w for line in selected for w in line.words)
    date_area = " ".join(w.text for w in words if w.center_x < table.description_left)
    date_match, time_match = DATE.search(date_area), TIME.search(date_area)
    raw_date = date_match[0] if date_match else TIME.sub("", date_area).strip(" |")
    raw_time = time_match[0] if time_match else ""
    parsed_date, parsed_time, issues = _date_time(raw_date, raw_time, table.page)
    description = " ".join(
        " ".join(
            w.text
            for w in line.words
            if table.description_left <= w.center_x < table.description_right
        )
        for line in selected
    ).strip()
    description = re.sub(r"\s+", " ", description)
    raw_amount = " ".join(
        w.text for w in words if table.amount_left <= w.center_x < table.amount_right
    )
    amount, direction, currency, amount_issues = _amount(raw_amount, table.page)
    issues.extend(amount_issues)
    kind = _entry_type(description, direction)
    issues.extend(_row_issues(description, kind, direction, table.page))
    bbox = (
        min(w.x0 for w in words),
        min(w.top for w in words),
        max(w.x1 for w in words),
        max(w.bottom for w in words),
    )
    source = Source(
        table.page,
        tuple(round(v, 3) for v in bbox),
        "\n".join(line.text for line in selected),
    )
    return Transaction(
        sequence=sequence,
        transaction_date=parsed_date,
        transaction_time=parsed_time,
        description=description,
        amount=amount,
        direction=direction,
        currency=currency,
        entry_type=kind,
        section=table.section,
        raw_date=raw_date,
        raw_time=raw_time,
        raw_amount=raw_amount,
        source=source,
        issues=tuple(issues),
    )


def _rows(table: Table, start_sequence: int) -> list[Transaction]:
    return [
        _transaction(table, selected, start_sequence + index)
        for index, selected in enumerate(_row_groups(table))
    ]


def _statement_date(full_text: str) -> date | None:
    match = re.search(
        r"Statement Date\s+(\d{1,2})\s+([a-z]{3}),?\s+(\d{4})",
        full_text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %b %Y").date()
    except ValueError:
        return None


def _coverage_issues(page: Page, found: list[Table]) -> list[Issue]:
    covered_words = {word for table in found for word in table.body}
    issues = []
    for line in lines(page.words):
        date_words = [w for w in line.words if DATE.search(w.text)]
        if (
            date_words
            and TIME.search(line.text)
            and any(word not in covered_words for word in date_words)
        ):
            issues.append(Issue("transaction_outside_supported_table", page.number))
    return issues


def _parse_page(
    page: Page, start_sequence: int
) -> tuple[list[Transaction], list[Issue], int]:
    transactions, issues = [], []
    if not page.text.strip() or not page.words:
        issues.append(Issue("page_without_selectable_text", page.number))
    found, table_issues = tables(page)
    issues.extend(table_issues)
    issues.extend(_coverage_issues(page, found))
    for table in found:
        rows = _rows(table, start_sequence + len(transactions))
        if not rows:
            issues.append(Issue("empty_transaction_table", page.number))
        transactions.extend(rows)
    return transactions, issues, len(found)


def parse_pages(
    pages: tuple[Page, ...], *, source_name: str, source_sha256: str, input_kind: str
) -> Statement:
    """Interpret extracted pages. The caller must supply the input's provenance."""
    full_text = "\n".join(p.text for p in pages)
    if not full_text.strip():
        raise ParseError("no_text", "No selectable text found; OCR is not supported.")
    if not re.search(r"\bHDFC\s+BANK\b", pages[0].text, re.IGNORECASE):
        raise ParseError(
            "unsupported_bank",
            "Only the observed HDFC statement layouts are supported.",
        )
    transactions, issues = [], []
    statement_date = _statement_date(full_text)
    if statement_date is None:
        issues.append(Issue("statement_date_missing_or_invalid"))
    table_count = 0
    for page in pages:
        page_rows, page_issues, page_table_count = _parse_page(
            page, len(transactions) + 1
        )
        transactions.extend(page_rows)
        issues.extend(page_issues)
        table_count += page_table_count
    if not table_count:
        raise ParseError(
            "unsupported_layout", "No supported HDFC transaction table found."
        )
    if not transactions:
        issues.append(Issue("no_transactions_extracted"))
    return Statement(
        source_name=source_name,
        source_sha256=source_sha256,
        input_kind=input_kind,
        page_count=len(pages),
        statement_date=statement_date,
        transactions=tuple(transactions),
        issues=tuple(issues),
    )
