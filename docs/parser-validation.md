# SBI and YES Bank: adapter and validation guide

## Scope and common contract

The observed selectable-text layouts are supported, not every historical or future
bank format. No OCR, duplicate-safe imports, categorization, funding allocation,
settlement, or unattended password storage is introduced.

The existing `parse_pdf(path, password=...)` and `parse_probe(path)` interfaces
return the same version-1 `Statement` contract described in the
[HDFC guide](hdfc-parser.md). Dispatch uses bank identity in statement content;
unknown or conflicting identity raises `unsupported_bank`. Filenames never select
an adapter. Parser versions are `sbi-0.1.0` and `yes-bank-0.1.0`; bank identifiers
are `sbi` and `yes_bank`.

Amounts remain nonnegative `Decimal` values and serialize as strings. Currency
comes from the amount heading, not the user's location. SBI and YES Bank print no
transaction times in these layouts, so time fields are null/empty without an
invented missing-time issue. Their source section is `transactions`.

## Implementation

- `core/sbi.py`: statement date below its positioned heading; printed transaction
  dates use named months and two/four-digit years. Two-digit years use Python's
  `%y` convention; observed samples are in 2026. No date is copied from another
  entry or inferred from a statement period.
- `core/yes_bank.py`: slash-separated dates and repeated transaction headings.
- `core/bank_table.py`: heading-based columns, nearest-baseline description
  continuations, source evidence, explicit amount markers, and coverage checks.
- `core/parser.py`: small bank dispatcher; the existing HDFC interpreter is
  unchanged. SBI/YES markers are never applied to HDFC's INR glyph/rewards.

SBI's source table can merge multiple entries into one ruled cell. Positioned
words, rather than the cell count, establish individual date/amount baselines.
An undated tax credit remains a separate undated transaction with a review issue.
Cardholder section captions and statement-period headings are not descriptions.
The printed EMI eligibility badge remains source text, not installment evidence.

YES Bank's merchant-category column is excluded from the description, but retained
in row provenance. It is not adopted as a spending-category decision. Wrapped
references are preserved; end-of-statement markers and contact footers are not
appended to the last row.

Explicit C/D and Cr/Dr markers determine direction, including a marker merged into
the numeric word by PDF extraction. Missing or unknown markers are not guessed
from the description. Unknown merchant credits are not automatically refunds.
Fees, interest, taxes, payments, refunds, cashback, and explicitly named
reversals/waivers remain distinguishable. Contradictory payment/credit-type
markers request review.

## Tests-first evidence

Before writing either adapter, synthetic tests and six opt-in original-PDF checks
were run against the HDFC-only parser and confirmed to fail. Existing regression
tests passed. Independent private expected rows were captured before bank adapter
code existed, without importing the production bank interpreters:

- SBI: complete date/description/amount/direction source-text rows inside the
  transaction section; no borrowing of dates for undated lines.
- YES Bank: independently extracted ruled cells for date, transaction details,
  merchant category, and amount; category cells do not become descriptions.

The encrypted originals are reopened with passwords held in memory. Every row is
checked for source order, date, full description, amount, direction, currency,
entry type, and page. Exact direction-separated totals and original-PDF SHA-256
are checked as well. Failure messages omit passwords and private row contents.
References live only in Git-ignored `data/expected/banks/`.

| Local source | Expected entries |
| :--- | ---: |
| `sbi_card_statement.pdf` | 3 |
| `sbi_card_statement_aug.pdf` | 10 |
| `sbi_card_statement_may.pdf` | 1 |
| `yes_bank_statement.pdf` | 14 |
| `yes_bank_statement_july.pdf` | 13 |
| `yes_bank_statement_sept.pdf` | 8 |

Each SBI original has image-only pages 3 and 4. Local rendered inspection found
promotional material, not transaction tables. The parser deliberately retains
`page_without_selectable_text` warnings: it cannot automatically prove that a new
image-only page is promotional. Original and August SBI samples also contain an
undated tax entry; generic merchant credits remain unknown. Do not suppress those
review flags to force a clean status.

Synthetic fixtures are invented and safe to commit. They exercise duplicate-looking
purchases, merged SBI regions, undated taxes, shifted/repeated headers, full wrapped
descriptions, malformed fields, explicit/unknown direction, unknown currency,
coverage warnings, exact totals, and encrypted/unencrypted PDFs for both banks.
Additional regressions cover a joined amount/marker token, a cardholder caption,
and the YES Bank end marker discovered during original-PDF verification.

## Run and review locally

```sh
uv run python -m unittest discover -s tests -v
HISAAB_PRIVATE_BANK_TESTS=1 uv run python -m unittest tests.test_bank_private -v
uv run python -m compileall -q core scripts tests
uv run python -m core parse data/sbi_card_statement.pdf data/yes_bank_statement.pdf
```

The six private checks skip unless explicitly enabled. They require private
references plus `SBI_PASS` and `YESBANK_PASS` literal assignments (optionally quoted)
in root `credit_card_cred.env`. The test helper parses the assignments without
executing shell code. The file is Git-ignored and should have owner-only mode
0600. It is a local verification convenience, not production secret management;
the normal CLI never reads it and still uses hidden terminal prompts.

Actual JSON exports and any rendered previews remain private under `data/`.
Permissions are not encryption. Never attach them or passwords to Linear/GitHub.
Check the output against the originals before approving the adapters. Exit 3 means
rows were saved but need review, not that extraction failed. Cross-page
continuations and arbitrary layout changes remain unvalidated; a successful open
or an issue-free status is not a universal completeness guarantee.
