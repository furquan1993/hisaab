"""Printed HDFC bill facts, kept separate from transaction spending."""

import re
from dataclasses import asdict, dataclass
from decimal import Decimal

from core.extraction import Page
from core.layout import lines
from core.models import Source


@dataclass(frozen=True)
class PrintedBalance:
    currency: str
    previous_balance: Decimal
    payments_and_credits: Decimal
    charges: Decimal
    finance_charges: Decimal
    amount_due: Decimal
    source: Source

    def __post_init__(self):
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Bill currency must be explicit.")
        for name in (
            "previous_balance", "payments_and_credits", "charges",
            "finance_charges", "amount_due",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or not 0 <= value < Decimal("1e18")
                or value.as_tuple().exponent < -2
            ):
                raise ValueError("Printed bill amounts must be exact nonnegative decimals.")

    def to_dict(self):
        return {
            key: format(value, ".2f") if isinstance(value, Decimal) else value
            for key, value in asdict(self).items()
        }


def parse_hdfc_balance(page: Page) -> PrintedBalance | None:
    """Read the observed five-column summary; ambiguous layouts stay unknown.

    The amount due is raised above the other four values in the observed PDFs,
    so text reading order cannot safely assign amounts to their labels.
    """
    phrases = (
        "PREVIOUS STATEMENT DUES", "PAYMENTS/CREDITS", "PURCHASES/DEBIT",
        "FINANCE CHARGES", "TOTAL AMOUNT DUE",
    )
    anchors = []
    for phrase in phrases:
        matches = []
        tokens = phrase.split()
        for line in lines(page.words):
            for index in range(len(line.words) - len(tokens) + 1):
                words = line.words[index : index + len(tokens)]
                if [word.text.upper() for word in words] == tokens:
                    matches.append(words)
        if len(matches) != 1:
            return None
        anchors.append(matches[0])
    centers = [(words[0].x0 + words[-1].x1) / 2 for words in anchors]
    tops = [min(word.top for word in words) for words in anchors]
    if centers != sorted(centers) or max(tops) - min(tops) > 12:
        return None
    boundaries = (
        [float("-inf")]
        + [(a + b) / 2 for a, b in zip(centers, centers[1:])]
        + [float("inf")]
    )
    values = []
    used = [word for words in anchors for word in words]
    for index, words in enumerate(anchors):
        low = max(word.bottom for word in words)
        candidates = [
            word for word in page.words
            if low < word.top < min(tops) + 45
            and boundaries[index] <= word.center_x < boundaries[index + 1]
        ]
        raw = " ".join(
            word.text
            for word in sorted(candidates, key=lambda word: (word.top, word.x0))
        )
        number = r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})\.\d{2}"
        amounts = re.findall(rf"(?:C|₹|INR)\s*({number})(?![\d,])", raw)
        # Never reinterpret a credit/negative balance as a positive amount due.
        if len(amounts) != 1 or re.search(r"\bCR\b|[-−]", raw, re.IGNORECASE):
            return None
        values.append(Decimal(amounts[0].replace(",", "")))
        used.extend(candidates)
    source = Source(
        page.number,
        tuple(round(value, 3) for value in (
            min(word.x0 for word in used), min(word.top for word in used),
            max(word.x1 for word in used), max(word.bottom for word in used),
        )),
        "\n".join(line.text for line in lines(tuple(used))),
    )
    try:
        return PrintedBalance("INR", *values, source)
    except ValueError:
        return None
