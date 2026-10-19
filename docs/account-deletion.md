# Delete an account

Open **Accounts**, choose **Delete** next to an account, and review the confirmation.
It lists every affected transaction across all dates and sources, including historical
or candidate statement rows. Cancel leaves everything unchanged. Confirming removes
the account from the account list and assignment choices and makes its transactions
unassigned. Categories, trips, descriptions, review corrections and original statement
facts remain intact. Archived accounts can also be deleted.

The preview must load successfully before confirmation is available. The server checks
the signed-in owner and a fingerprint of the account and affected transactions under
locks. If anything changes after preview, cancel and reopen Delete to review the
updated list. Unassignment and account removal happen atomically; each decision's
version advances and its before/after audit event records the deleted account.
History learning is cleared for this account and explicit empty assignments protect
these transactions from automatic reassignment.

The database retains an irreversible account tombstone for reconciliation receipts
and historical identifiers. Deleted accounts cannot be restored through label editing;
their existing names remain reserved. Existing receipts and decision history are
preserved and remain available for review.

## Rollout

The approved `0017_account_deletion` rollout completed on 2026-10-19, following
`0016_friendly_descriptions`. A fresh owner-private backup was checksummed, restored
into a password-protected temporary local PostgreSQL database, and used to rehearse
the exact migration before live application. Existing records, original PDFs,
assignments and financial view results were verified unchanged. Authenticated
preview/delete and stale-token checks used synthetic records in rolled-back
transactions; no real account was deleted and no probe records were retained.
Anonymous execution remains denied. The temporary restore was removed after
verification. Private recovery evidence is retained under Git-ignored
`data/migration-rollout/account-deletion-verified-backup.json`.

The missing live functions caused the initial “Could not load affected transactions”
error; the installed migration enables the existing frontend button. The local client
also now identifies a missing database upgrade explicitly instead of suggesting a
retry. Future rollouts follow [the browser workspace guide](browser-workspace.md).
Downgrade refuses to resurrect deleted accounts; use a reviewed restore when necessary.

## Verification

- `tests/test_account_deletion.py`: disposable PostgreSQL preview, more than one page,
  owner isolation, stale confirmation, atomic unassignment, audit and receipt retention.
- `web/src/Labels.delete.test.tsx`: preview, cancel, confirm, loading failures, conflicts
  and empty accounts.
- `web/e2e/account-delete-smoke.mjs`: desktop/mobile synthetic demo flow, modal focus,
  cancellation and account unassignment.
