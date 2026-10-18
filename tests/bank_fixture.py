"""Invented SBI/YES Bank evidence. No private rows, references, or passwords."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth

from core.extraction import Page, Word
from core.parser import parse_probe


class BankPage:
    def __init__(self, bank, *, number=1, shift=0):
        self.bank = bank
        self.number = number
        self.shift = shift
        self.fragments = []
        self.add("SBI CARD" if bank == "sbi" else "YES BANK", 20, 20)
        if bank == "sbi":
            self.add("Credit Limit Statement Date", 210, 50)
            self.add("23 Sep 2026", 270, 67)
        else:
            self.add("Statement Date : 12/10/2026", 20, 50)

    def add(self, text, x, top):
        self.fragments.append((text, x + self.shift, top))

    def header(self, top=200):
        if self.bank == "sbi":
            self.add("Date", 33, top)
            self.add("Transaction Details", 177, top)
            self.add("Amount ( ` )", 369, top)
            self.add("for Statement Period: 24 Aug 26 to 23 Sep 26", 155, top + 10)
        else:
            for text, x in [
                ("Date", 48),
                ("Transaction Details", 93),
                ("Merchant Category", 377),
                ("Amount (Rs.)", 491),
            ]:
                self.add(text, x, top)

    def row(
        self,
        top,
        description="SYNTHETIC SHOP",
        amount="123.45",
        *,
        day=None,
        marker=None,
        wrapped=False,
        category="",
    ):
        is_sbi = self.bank == "sbi"
        if day is None:
            day = "01 Sep 26" if is_sbi else "01/10/2026"
        if marker is None:
            marker = "D" if is_sbi else "Dr"
        date_x, description_x = (18, 66) if is_sbi else (48, 93)
        if day:
            self.add(day, date_x, top)
        if description:
            self.add(description, description_x, top - 4.5 if wrapped else top)
        if wrapped:
            self.add("SYNTHETIC-REFERENCE", description_x, top + 4.5)
        if not is_sbi and category:
            self.add(category, 377, top)
        if amount is not None:
            right = 403 if is_sbi else 536
            self.add(amount, right - stringWidth(amount, "Helvetica", 7), top)
        if marker:
            self.add(marker, 418 if is_sbi else 539, top)

    def footer(self, top):
        text = (
            "Transactions highlighted in grey color, if any, do not form part of Purchases"
            if self.bank == "sbi"
            else 'SMS "Help" space <CUSTID>'
        )
        self.add(text, 20, top)
        self.add("Important Information", 20, top + 16)
        self.add("Illustrative finance charges 9,999.99", 20, top + 30)

    def page(self):
        words, grouped = [], {}
        for text, x, top in self.fragments:
            grouped.setdefault(top, []).append((x, text))
            for token in text.split():
                width = stringWidth(token, "Helvetica", 7)
                words.append(Word(token, x, top, x + width, top + 7))
                x += width + stringWidth(" ", "Helvetica", 7)
        text = "\n".join(
            " ".join(text for _, text in sorted(grouped[top]))
            for top in sorted(grouped)
        )
        return Page(self.number, text, tuple(words))

    def probe_record(self):
        page = self.page()
        return {
            "page": page.number,
            "text": page.text,
            "words": [asdict(word) for word in page.words],
        }


def parse(*pages):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "neutral-name.json"
        path.write_text(
            json.dumps(
                {
                    "source": "neutral-name.pdf",
                    "pages": [page.probe_record() for page in pages],
                }
            )
        )
        return parse_probe(path)
