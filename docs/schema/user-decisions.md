# User decisions alongside immutable evidence

The approved hosted database rollout is complete through `0013_auto_assignments`.
The approved automatic-assignment rollout preserved all prior decisions and financial
records; see [history training and correction learning](../automatic-assignments.md).
Future migrations require separate review and rollout approval.

The original five evidence entities remain intact. New owner-scoped sidecars hold Categories, funding Accounts, current entry decisions and append-only decision events. Accounts are budget/funding pots, never aliases for credit cards. The two label kinds are independently managed and assigned.

## Labels and assignments

Trips and related spending use independent owner-scoped groups and versioned
membership rather than overloading Categories or funding Accounts. See
[the Spending model, usage and rollout boundary](../spending.md). Group edits do
not change financial decisions or train automatic category/account assignments.

* `hisaab_api.labels` lists both kinds, including archived labels.
* `save_label` creates at expected version zero, or renames/archives/restores an existing label at its exact expected version. Names are unique per owner and kind through the managed mutation API, case-insensitively. Archived names remain reserved.
* `save_entry_decision` accepts an entry ID, expected decision version, and a patch. Omitted assignment keys retain their current values; explicit null removes an assignment. It derives ownership from verified authentication, checks the selected source, locks the statement and decision, validates same-owner labels, and writes a decision plus audit event atomically.
* Archived labels remain visible on historical assignments. They cannot be newly assigned until restored.
* Category and Account assignment never changes original facts, parser issues or review readiness. Browser clients cannot write evidence, PDFs, ownership, decision rows or audit rows directly.
* A stale version returns HTTP 409. There is no silent last-write-wins behavior. The browser keeps an unsuccessful draft open for explicit review rather than replacing it with a success state.

All new tables retain owner RLS. API views are security invoker; mutation functions use a fixed empty search path, explicit ownership checks, and restricted execute grants. Auth subjects recorded in audit are provenance, not financial-owner identifiers or managed Auth foreign keys.

## Revision boundary

Current decisions reference immutable logical entry roots with restrictive foreign keys. Ordinary duplicate imports still do not reparse or replace records. Explicit reparsing creates new immutable evidence rows and a pending comparison, borrowing the retained original through a same-owner/card/bill/fingerprint reference rather than copying PDF bytes. Full-provenance matches are automatic only when unique on both sides and at the same sequence position. Everything else requires explicit identity or new-entry decisions and acknowledgement of removed rows. Acceptance checks the published source and complete evidence hashes, inserts immutable lineage bindings, and changes the selected source atomically. Earlier evidence and decisions remain present. Source evidence IDs may change; the separately exposed logical entry ID and decision record identity are preserved.

Revision APIs and explicit reparse CLI now have isolated PostgreSQL and actual Auth/API coverage. The source-comparison UI now supports explicit identity/removal review, acceptance/rejection and inspection of retained extraction history. Reasoned corrections and independent statement coverage/date reviews are now implemented. Original fields remain unchanged, supported issues resolve against reviewed values, stale source-bound corrections stay preserved but unapplied, and statement review snapshots are append-only. The browser offers explicit original/reviewed date filtering. Funding totals and contribution settlement use derived views and minimal receipt/confirmation sidecars. Revisions `0010_funding_totals` and `0011_contributions` were separately approved and deployed after verified recovery and funding-flow rehearsal. See [the reconciliation contract](../reconciliation.md). Label assignments alone never imply that contributions have been received.

## References

* https://www.postgresql.org/docs/17/sql-createfunction.html
* https://www.postgresql.org/docs/17/sql-createview.html
* https://www.postgresql.org/docs/17/explicit-locking.html
* https://postgrest.org/en/stable/references/errors.html

## Friendly descriptions

[Personal transaction descriptions](../friendly-descriptions.md) use independent,
append-only snapshots and versions. They never change financial decision versions,
merchant learning or settlement fingerprints. Hosted rollout is pending approval.
