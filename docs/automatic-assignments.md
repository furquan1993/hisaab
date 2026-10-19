# Automatic account and category assignments

Migration `0013_auto_assignments` adds private owner-scoped learning examples. It was
applied to the hosted database on 2026-10-19 after explicit approval, a fresh private
backup, a byte-verified isolated restore and a full training rehearsal.
Historical workbooks remain reference material: training creates labels and
learning examples, never old transactions, receipts, or contribution balances.

## Behavior

Accounts and categories are learned independently. Matching uses normalized full
merchant descriptions and debit/credit direction. Punctuation, case and long
numeric references are normalized; arbitrary fuzzy merchant matching is avoided.
A historical match needs at least two examples and at least 90% agreement. A lone
example, conflicting history below that threshold, unknown descriptions, unknown
entry types and card repayments remain unassigned.

The latest explicit manual correction for the same merchant and direction takes
precedence over workbook history. Choosing Unassigned teaches an explicit removal.
Existing assignments are preserved, as are existing manual decisions at migration
time, including empty fields. Clearing an automatic label prevents it being
reapplied to that entry. Changing one label does not teach the other label.
Archived labels are never newly assigned; restoring them makes them eligible again.

Because the supplied workbooks have no category column, starter rules cover clear
merchant names: Instamart/BigBasket/Blinkit/Zepto for Groceries, Swiggy/Zomato for
Dining, IRCTC/Uber/Ola for Transport, petrol/petroleum/fuel for Fuel, Netflix/Spotify
for Subscriptions. Parsed fees/taxes, interest and cashback have their corresponding
categories. Generic Amazon Pay and unknown merchants have no guessed category.
These are initial conventions and can be corrected in the ordinary selectors.
Starter categories are created only when needed; archived categories stay archived.
A learned category, including an explicit removal, suppresses starter rules.

All writes are persisted in the existing decisions and append-only audit events.
Automatic events have no human actor and identify automatic assignment in their
reason. Extracted facts, review issues, overrides and acknowledgements are preserved.
Automatic assignments affect the existing derived account/reconciliation totals;
they never confirm funding or create contributions. Existing settlement fingerprints
still require review when obligations change.

## Training and backfill

Preview is read-only and does not connect to the database or read its configuration:

```sh
uv run python -m core assignment-train --owner OWNER_UUID \
  'data/reference/Credit Card Statements 2024.xlsx' \
  'data/reference/Credit Card Statements 2025.xlsx' \
  'data/reference/Credit Card Statements 2026.xlsx'
```

After a reviewed migration rollout, add `--apply` to save examples and backfill
selected transactions. Training is atomic and re-running identical files is
idempotent. Source identifiers include a workbook content hash, sheet and row.
Editing a workbook changes its source identifiers: do not retrain modified copies
as additional independent evidence without reviewing the duplication.
Names match existing labels case-insensitively. Archived labels are skipped and
reported as a count. Output includes only counts, never descriptions or amounts.
A workbook preview counts qualifying historical patterns, not expected ledger hits.

New entries are assigned when their source is selected, including after an explicit
source revision. Existing entries can also be assigned in batches of at most 50
through `auto_assign_entries(p_entry_ids, p_expected_owner)`. The browser invokes
this for the displayed page and reloads saved values after confirmed changes.
When assignment fails, the ledger stays available and shows a retry message.
There is no background browser retry loop and no fallback to synthetic data.

## Security, concurrency and rollback

Only the trusted operator can load workbook examples. Browser writes use the
existing authenticated decision API; the assignment RPC checks captured owner
context. Helpers and examples are not browser-accessible. All examples carry an
owner and same-owner label/entry foreign keys, and the table has RLS enabled.

Assignments, revisions, reviews and settlements serialize on statement rows.
Batch assignment and training acquire statement locks in stable order before
label locks. Training backfills the statement set captured at the start. Automatic
category work uses the same owner/category advisory lock as label management.
Manual saves retain optimistic version checks; stale edits cannot overwrite an
automatic assignment. Automatic assignments are idempotent and never become manual
training examples themselves.

Backups include the new table and functions through the existing app-schema backup.
Downgrade refuses to discard learned examples. Use a verified pre-rollout restore
for a populated database rather than deleting learning or audit history.

## Verification

Synthetic tests cover XLSX layout changes, signed credits, formula-error rows,
consensus and ambiguity, archived labels, independent categories, explicit removal,
latest manual corrections, source selection, retained review corrections, idempotent
training, audit events and owner isolation. Authenticated HTTP tests exercise the
actual RPC permissions and validation. Real browser tests verify automatic assignment, persisted reloads and explicit
removal. A native backup/restore drill includes populated learning examples.
No real workbook rows are committed as tests.

Sources: [PostgreSQL function security](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY),
[trigger functions](https://www.postgresql.org/docs/17/plpgsql-trigger.html),
[Supabase RPC](https://supabase.com/docs/reference/javascript/rpc).

## Hosted rollout verification

The approved rollout loaded the existing 2024–2026 workbook examples and backfilled
five selected transactions: two account assignments and five category assignments.
The live results matched the rehearsal. Every original record, PDF byte, existing
decision and contribution record was preserved. Repeated training and authenticated
batch assignment produced no further changes. All 68 selected entries were checked,
and the new learning table and internal helpers remain inaccessible to browser roles.
The private rollout manifest and backup remain under Git-ignored `data/`.

On 2026-10-19, a separately approved account-name consolidation reduced the active
account list from 56 to 38. Eighteen duplicate labels were archived and 277 learning
examples were remapped to their approved canonical accounts. The excluded funding
group and every current transaction assignment were preserved. The exact approved
mapping and verified backup remain private under Git-ignored `data/migration-rollout/`.
Archived labels remain visible in label management for historical reference; regular
assignment selectors show active labels.
