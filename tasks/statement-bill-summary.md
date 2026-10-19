# Statement bills alongside spending

Implementation and the separately approved hosted rollout are complete.

The Summary page labels transaction totals as **Net spending this cycle** or
**Net spending in month** and states that previous balances and repayments are
excluded. In statement mode it independently shows each selected bill's printed
amount due and an expandable arithmetic breakdown. Differences are explicit;
unsupported headers and absent bill evidence remain unknown.

## Approved hosted rollout

1. Take a fresh application backup and verify that it restores into an isolated
   database before touching the hosted schema.
2. Confirm the hosted revision is `0013_auto_assignments`; apply only
   `0014_statement_balances`. Its SQL is prepared privately at
   `data/migration-rollout/0014_statement_balances.sql`.
3. Preview and then capture the two verified HDFC statement balances in
   `data/validation/statement-balances-plan.json`. Recheck PDF and probe hashes,
   parsed header values, all retained transaction evidence and source selection
   before applying. Verify the complete retained transaction set.
4. Verify metadata drift, API owner isolation, selected-source visibility and
   the selected statement's Summary values against the private verification plan.
   Preserve any difference between printed due and header arithmetic explicitly.
5. Confirm transaction rows, assignments and selected source IDs are unchanged.

The migration adds one nullable JSON field on imports and one read-only API view.
It preserves existing source fields and browser write restrictions. New imports
and reparse candidates capture supported printed headers automatically. Existing
records require the explicit, previewable capture step.

A downgrade refuses to discard captured bill evidence. If a rollout needs to be
reversed, review/export that evidence first or use the verified pre-rollout
backup. The frontend keeps spending available when the bill view is unavailable.

## Verification completed

- Python unit and disposable PostgreSQL suite: 281 tests, 60 environment-gated
  skips, all executed tests passed.
- Separate disposable Supabase Auth/API test: owner isolation, selected sources,
  anonymous/unmapped denial and read-only access passed.
- Frontend: 58 tests, production build and formatting passed.
- Browser checks: synthetic desktop/mobile bill and spending panels passed.
- Read-only hosted preflight: current revision `0013_auto_assignments`; two
  selected HDFC imports verified against PDF fingerprints and stored extraction.

## Hosted verification — completed 2026-10-19

The user explicitly approved this rollout. A fresh application backup at
`data/exports/run-bbhhxbqj/database.dump` was checksummed and restored into a new,
isolated PostgreSQL database. Every application table and row fingerprint,
including original PDF bytes, matched the source. The API views and RLS flags
matched as well. Migration, metadata drift checks, and both balance captures
passed rehearsal before hosted writes.

The hosted migration and the two captures committed together. Independent
post-commit verification confirmed revision `0014_statement_balances`, both
printed-balance payloads, no metadata drift, and unchanged fingerprints for every
existing transaction, assignment, review, receipt and selected source. The new
bill view passed real-owner and unmapped-identity checks under the authenticated
database role. Anonymous reads and browser writes remain denied.

The stored spending, printed amount due, and header arithmetic difference were
verified against the original statements. Actual financial amounts remain private.
The private verification report is
`data/validation/statement-balances-rollout.json`; the retained operational
procedure is `data/validation/rollout_statement_balances.py`.

Future Auth/API migrations and real financial loads still require separate
reviewed rollout approval under README.md.
