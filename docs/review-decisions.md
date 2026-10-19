# Verified review decisions

Implementation is not a hosted deployment. New migrations and permissions require a separately reviewed and approved rollout.

## Entry corrections

Use Review on a selected-source row. Supported corrections are transaction date/time, description, absolute amount, debit/credit direction, currency and entry type. Money remains decimal text over the managed API. A reason is required; invalid dates, unsupported fields, invalid currencies and floating-point amounts are rejected. Blank fields restore extracted values.

Original fields, source text, PDF bytes and parser issues do not change. Supported issues resolve against verified effective values. Missing facts cannot be dismissed with a checkbox. Account and Category assignments remain independent and never resolve extraction warnings.

Saves check the shared entry decision version and selected source. A conflict keeps the draft open and does not overwrite newer work. Each successful change records the verified actor, reason and before/after decision snapshot. Browser clients cannot update decision or audit tables directly.

## Statement review

From Imports, use Review statement on the selected extraction. Correct the bank's printed generation/issue date only after checking the original; do not enter its payment due date. Coverage acknowledgements require a reason and mean the user verified that no transactions are missing. Otherwise leave the warning pending and correct the import.

Statement review snapshots are append-only and separately versioned. They are scoped to the original file family and full coverage/date evidence fingerprint. An unchanged reparse retains acknowledgements; changed evidence preserves prior snapshots but does not silently apply them.

## Revision and filter behavior

Entry corrections are anchored to stable logical identities and their reviewed evidence fingerprint. Unchanged accepted reparses preserve them. Changed evidence retains the prior corrections in history but exposes them as stale, unapplied values until the user explicitly reviews the new source.

Both date views retain original extracted-date filtering by default. The explicit Filter dates control can instead use reviewed dates. Corrected values are shown alongside originals. These browsing choices do not redefine reconciliation periods: a statement belongs to the month the bank generated/issued it, for every month, never purchase/payment/upload/parser-run months.

## Safety checks

Actual isolated Auth/API/browser tests cover verified corrections, separate coverage actions, exact decimal values, reload/reparse persistence, stale evidence/version conflicts, retained originals, and foreign/unmapped subjects. The public client sends a captured owner-context guard when creating labels; that guard detects a changed browser session and never authorizes or selects an owner. Authorization always comes from the verified session mapping.

Synthetic demo changes are memory-only and reset on reload/exit. There is no fallback from failed live reads to fabricated demo records. No new hosted schema, permission or financial-data writes are performed by implementing or testing this feature.
