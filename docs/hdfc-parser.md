# HDFC parser: review guide

## Scope

Support the supplied selectable-text HDFC Regalia and HDFC Swiggy PDFs, including their password protection, page offsets, optional rewards column, repeated transaction headings, and wrapped international-section tax description. No database, ownership/authentication, import deduplication, categorization, funding assignment, email fetching, OCR, or scheduler is added here.

The supported unit is the observed statement layout, not every historical HDFC format. Unknown headers, empty extraction pages, malformed fields, and transaction-looking lines outside supported tables surface as failures or review issues. Arbitrary layout changes cannot all be detected; inspect new statement formats before treating them as supported. Descriptions that continue across a page boundary are not currently supported or validated. Do not infer support from a successful PDF open alone.

## Files to review

- `core/models.py`: immutable transaction/evidence contract and exact JSON serialization.
- `core/extraction.py`: PDF opening, word extraction, safe errors, and probe JSON boundary validation.
- `core/layout.py`: table/column discovery from each page's headings.
- `core/hdfc.py`: geometric row assembly, amount/direction interpretation, conservative entry types, and coverage warnings.
- `core/parser.py`: public PDF/probe entry points.
- `core/cli.py`, `core/__main__.py`: local command.
- `core/output.py`: private, nonoverwriting JSON export.
- `tests/test_models.py`, `tests/test_hdfc.py`, `tests/test_parser.py`: synthetic regression tests.
- `tests/hdfc_fixture.py`: invented source layouts and actual generated PDF fixtures.
- `tests/test_hdfc_private.py`: optional private sample validation; skips on a checkout without private reference data.

The existing diagnostic probe is unchanged. Runtime dependencies are unchanged.

## Public API

```python
from core.parser import parse_pdf, parse_probe

# Obtain the password privately. Do not hard-code or log real passwords.
statement = parse_pdf(path, password=password)
data = statement.to_dict()

# Diagnostic alternative using an existing extraction snapshot:
statement = parse_probe(probe_path)
```

`parse_pdf` and `parse_probe` return a `Statement`. Expected input/decryption/extraction failures raise `ParseError` with a safe machine-readable `code`. The CLI also sanitizes unexpected exceptions instead of dumping dependency tracebacks or document contents.

PDF bytes and passwords are handled in memory; no decrypted PDF is written. The local command first tries an empty password, then prompts with hidden input only if a terminal is available. Noninteractive encrypted inputs return `password_required`; unattended secret storage is deferred.

## JSON contract, version 1

The envelope includes `schema_version`, `parser_version`, `bank`, `source_name`, `source_sha256`, `input_kind`, `page_count`, nullable `statement_date`, ordered `transactions`, statement-level `issues`, `status`, `totals`, and `unresolved_amount_count`.

Each transaction contains:

| Field | Meaning |
| :--- | :--- |
| `sequence` | One-based source order across pages/sections; not a persistent transaction ID. |
| `transaction_date`, `transaction_time` | ISO date/time or null when missing/invalid; no timezone conversion. |
| `description` | Source description words joined into one string, without merchant normalization. |
| `amount` | Nonnegative exact decimal serialized as a string, or null. Never a binary float. |
| `direction` | `debit`, `credit`, or null when ambiguous. Separate from the unsigned amount. |
| `currency` | Identified currency or null; no conversion or default from a dollar symbol alone. |
| `entry_type` | `purchase`, `payment`, `refund`, `cashback`, `fee`, `interest`, `tax`, `reversal`, or `unknown`. |
| `section` | `domestic` or `international` source section; not a currency classification. |
| `raw_date`, `raw_time`, `raw_amount` | Source field tokens for review. |
| `source` | One-based page, bounding box in PDF points `(x0, top, x1, bottom)`, and raw row text including wraps. |
| `issues` | Machine-readable issue codes with page references. |

`status=parsed` means there are no known issues, not proof of universal layout support. `needs_review` can mean an unknown semantic entry type even when its date/amount/direction are all parsed correctly. Totals are separated by currency and include only rows whose amount and direction are known. `unresolved_amount_count` also counts unknown currency. Totals are transaction sums, not bill balances or settlement requirements; they deliberately include payments and credits.

For `input_kind=pdf`, the fingerprint identifies the original encrypted PDF bytes. For `input_kind=probe`, it identifies the diagnostic JSON bytes, NOT the original PDF. A probe snapshot is never silently substituted when PDF parsing fails. File names and sequences are not stable card/owner/import identities; those belong to later import work.

No categories, funding sources, learned decisions, or settlement values are embedded in these parsing facts.

## Observed HDFC conventions

- `+` in the amount column denotes a credit. A separate `+` in the rewards column must never change transaction direction.
- The original PDFs extract a rupee glyph as `C`. It denotes INR in these layouts, NOT a credit marker.
- Column locations are discovered separately for each header because the first page, subsequent pages, and the two variants differ.
- Right-aligned amounts have room for a leading credit sign; rewards are excluded from the amount region.
- Description lines can sit above and below their date/amount baseline. They are associated using neighboring row anchors rather than text-line order alone.
- The printed EMI eligibility badge is retained in the description. It is not classified as an installment transaction.
- Cashback and explicitly named repayments are distinguishable. A generic merchant credit without refund evidence remains `unknown` with a review issue.
- Source order is preserved, including international entries dated earlier than preceding domestic entries. No deduplication or chronological reordering occurs.
- Marketing text, summary rows, EMI-conversion totals, and cashback/GST summaries are not additional transactions.

## Validation evidence

The local private references are in Git-ignored `data/expected/hdfc_rows.json`. Amounts, direction, dates, times, entry types, and description prefixes were manually transcribed from readable extraction text, independently of production geometry parsing. Full descriptions were independently reconstructed from those text lines and checked against the manual prefixes. This is not a fresh visual inspection or decryption of the real originals.

Local tests check every expected row, full description, source page, currency, exact debit/credit totals, and review issues: 27 Regalia entries and 15 Swiggy entries. Regalia has two credits without enough description evidence to infer their type, so the result correctly requests review. Neither sample has unresolved amounts in these extraction checks.

Two additional Regalia extraction snapshots were independently checked after the initial implementation: August has 22 entries (18 debits, 4 credits), and September has 41 entries (25 debits, 16 credits). A separate text-line check matched every date, time, full description, amount, direction, currency, and source page, plus exact debit/credit totals. Both have zero unresolved amounts and no statement-level parsing issues. Their 3 and 15 row-level review flags respectively are unknown merchant-credit entry types, not missing transactions. Negative rewards adjustments and wrapped tax descriptions were handled without parser changes. These additional checks are local validation evidence, not committed regression fixtures or automated fresh decryption of the originals.

Synthetic tests generate real PDFs, including AES-256 password protection, and cover both rewards layouts, distinct identical-looking purchases, page offsets, multiline descriptions, unknown/malformed fields, Indian number grouping, large credits, missing table captions, empty pages, safe failures, private output permissions, hidden password prompting, and explicit sensitive-output opt-in. CLI regression tests also check failure/review exit-code precedence in every input order, cancellation preserving earlier results, and sanitized unexpected/output failures.

Run:

```sh
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q core scripts tests
```

The two private checks skip without the ignored reference file. Do not copy the private reference or extraction JSON into committed fixtures. End-to-end verification of the real encrypted originals is still a local review step:

```sh
uv run python -m core parse data/hdfc_regalia_statement.pdf data/hdfc_swiggy_statement.pdf
```

Open the saved JSON files and compare them with the original statements. Exit 3 means results were saved and flagged for review, not that extraction failed. Actual financial exports are plaintext with owner-only file/directory permissions, not encrypted at rest.

## Official extraction documentation

Uses pdfplumber 0.11.10's documented `open(..., password=...)`, `extract_text()`, and `extract_words()` APIs:

- https://github.com/jsvine/pdfplumber/tree/v0.11.10
- https://github.com/jsvine/pdfplumber/blob/v0.11.10/README.md#loading-a-pdf
- https://github.com/jsvine/pdfplumber/blob/v0.11.10/README.md#extracting-text

No statement contents are uploaded to an external service.
