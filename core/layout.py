"""Small geometry helpers for the observed HDFC layouts, not a table engine."""

import re
from dataclasses import dataclass

from core.extraction import Page, Word
from core.models import Issue


@dataclass(frozen=True)
class Line:
    words: tuple[Word, ...]

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def lines(words: tuple[Word, ...]) -> list[Line]:
    """Group baselines within two points; preserve separate wrapped text lines."""
    grouped: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if not grouped or abs(word.top - grouped[-1][0].top) > 2:
            grouped.append([])
        grouped[-1].append(word)
    return [Line(tuple(sorted(group, key=lambda w: w.x0))) for group in grouped]


@dataclass(frozen=True)
class Table:
    page: int
    section: str
    date_left: float
    description_left: float
    description_right: float
    amount_left: float
    amount_right: float
    body: tuple[Word, ...]


def tables(page: Page) -> tuple[list[Table], list[Issue]]:
    """Locate each table from its caption and repeated column headings.

    Page 1 and later pages have different offsets. Column boundaries come from
    their own headings; no page-specific coordinates or bank account IDs.
    """
    all_lines = lines(page.words)
    found, issues = [], []
    for index, caption in enumerate(all_lines):
        if caption.text.lower() not in (
            "domestic transactions",
            "international transactions",
        ):
            continue
        candidates = [
            line for line in all_lines[index + 1 :] if 0 < line.top - caption.top < 35
        ]
        header = next(
            (
                line
                for line in candidates
                if {"DATE", "TIME", "TRANSACTION", "DESCRIPTION", "AMOUNT"}
                <= {w.text.upper() for w in line.words}
            ),
            None,
        )
        if header is None:
            issues.append(Issue("unsupported_table_header", page.number))
            continue
        headings = {w.text.upper(): w for w in header.words}
        start = max(w.bottom for w in header.words)
        end = float("inf")
        for line in all_lines:
            if line.top <= start:
                continue
            label = line.text.lower()
            if (
                label in ("domestic transactions", "international transactions")
                or label.startswith("transactions total amount")
                or label.startswith("*transaction time")
                or re.match(r"^page \d+ of \d+", label)
                or label.startswith(("cash back summary", "gst summary"))
            ):
                end = line.top
                break
        # Leave room for the leading credit sign on large right-aligned
        # amounts; a midpoint can clip it and turn a credit into a debit.
        amount = headings["AMOUNT"]
        reward = headings.get("REWARDS")
        amount_left = reward.x1 + 3 if reward else amount.x0 - 45
        description_left = (headings["TIME"].x1 + headings["TRANSACTION"].x0) / 2
        description_right = reward.x0 if reward else amount_left
        amount_right = headings["PI"].x0 - 1 if "PI" in headings else amount.x1 + 5
        if not (
            headings["DATE"].x0
            < description_left
            < description_right
            <= amount_left
            < amount_right
        ):
            issues.append(Issue("unsupported_column_order", page.number))
            continue
        body = tuple(
            w
            for line in all_lines
            if start < line.top < end and "CKYC" not in line.text.upper()
            for w in line.words
            if headings["DATE"].x0 - 2 <= w.center_x < amount_right
        )
        found.append(
            Table(
                page.number,
                caption.text.split()[0].lower(),
                headings["DATE"].x0,
                description_left,
                description_right,
                amount_left,
                amount_right,
                body,
            )
        )
    return found, issues
