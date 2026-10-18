"""Invented statement layouts, shaped like the samples but containing no PII."""

from dataclasses import asdict
from io import BytesIO

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from core.extraction import Page, Word


class HdfcPage:
    def __init__(self, *, rewards=True, shifted=False, number=1):
        self.fragments = []
        self.rewards = rewards
        self.number = number
        self.date_x = 169.5 if shifted else 25.5
        self.description_x = (
            (250.7 if shifted else 136.3) if rewards else (260.2 if shifted else 149)
        )
        self.rewards_x = 463.1 if shifted else 428.2
        self.amount_x = 530.3 if shifted else 524.5
        self.amount_right = self.amount_x + 27.7
        self.add("HDFC BANK", 25, 25)
        self.add("Statement Date 13 Oct, 2026", 25, 40)

    def add(self, text, x, top):
        self.fragments.append((text, x, top))

    def header(self, top=200, section="Domestic"):
        self.add(f"{section} Transactions", self.date_x, top)
        for text, x in [
            ("DATE & TIME", self.date_x),
            ("TRANSACTION", self.description_x),
            ("DESCRIPTION", self.description_x + 58),
            ("AMOUNT", self.amount_x),
            ("PI", self.amount_right + 13),
        ]:
            self.add(text, x, top + 16)
        if self.rewards:
            self.add("REWARDS", self.rewards_x, top + 16)
        self.add("EXAMPLE HOLDER [CKYC ID : EXAMPLE]", self.date_x, top + 30)

    def row(
        self,
        top,
        description="SYNTHETIC SHOP",
        amount="123.45",
        *,
        day="01/10/2026",
        clock="12:30",
        credit=False,
        reward=None,
        currency="C",
        suffix="",
        wrapped=False,
    ):
        if day:
            self.add(day + "|", self.date_x, top)
        if clock:
            self.add(clock, self.date_x + 40, top)
        if wrapped:
            self.add(description, self.description_x, top - 4.3)
            self.add("SYNTHETIC-REFERENCE)", self.description_x, top + 4.3)
        else:
            self.add(description, self.description_x, top)
        if reward is not None:
            self.add("+ " + str(reward), self.rewards_x + 7, top)
        if amount is not None:
            text = (
                ("+ " if credit else "")
                + currency
                + " "
                + amount
                + (" " + suffix if suffix else "")
            )
            self.add(text, self.amount_right - stringWidth(text, "Helvetica", 7), top)
        self.add("l", self.amount_right + 13, top + 0.7)

    def footer(self, top):
        self.add("TRANSACTIONS TOTAL AMOUNT", 250, top)
        self.add("Eligible for EMI CONVERT TO EMI", 250, top + 14)
        self.add("99 C 9,99,999.99", 400, top + 28)
        self.add("Page 1 of 1", 250, top + 45)

    def page(self):
        words = []
        for text, x, top in self.fragments:
            for token in text.split():
                width = stringWidth(token, "Helvetica", 7)
                words.append(Word(token, x, top, x + width, top + 7))
                x += width + stringWidth(" ", "Helvetica", 7)
        grouped = {}
        for text, x, top in self.fragments:
            grouped.setdefault(top, []).append((x, text))
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
            "words": [asdict(w) for w in page.words],
        }


def pdf_bytes(pages):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(620, 900))
    for page in pages:
        canvas.setFont("Helvetica", 7)
        for text, x, top in page.fragments:
            canvas.drawString(x, 900 - top - 7, text)
        canvas.showPage()
    canvas.save()
    return output.getvalue()
