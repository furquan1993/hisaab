# User decisions alongside immutable evidence

Implementation in progress. These changes are not deployed to the hosted project.

The original five evidence entities remain intact. New owner-scoped sidecars hold Categories, funding Accounts, current entry decisions and append-only decision events. Accounts are budget/funding pots, never aliases for credit cards. The two label kinds are independently managed and assigned.

## Labels and assignments

* `hisaab_api.labels` lists both kinds, including archived labels.
* `save_label` creates at expected version zero, or renames/archives/restores an existing label at its exact expected version. Names are unique per owner and kind through the managed mutation API, case-insensitively. Archived names remain reserved.
* `save_entry_decision` accepts an entry ID, expected decision version, and a patch. Omitted assignment keys retain their current values; explicit null removes an assignment. It derives ownership from verified authentication, checks the selected source, locks the statement and decision, validates same-owner labels, and writes a decision plus audit event atomically.
* Archived labels remain visible on historical assignments. They cannot be newly assigned until restored.
* Category and Account assignment never changes original facts, parser issues or review readiness. Browser clients cannot write evidence, PDFs, ownership, decision rows or audit rows directly.
* A stale version returns HTTP 409. There is no silent last-write-wins behavior. The browser keeps an unsuccessful draft open for explicit review rather than replacing it with a success state.

All new tables retain owner RLS. API views are security invoker; mutation functions use a fixed empty search path, explicit ownership checks, and restricted execute grants. Auth subjects recorded in audit are provenance, not financial-owner identifiers or managed Auth foreign keys.

## Revision boundary

Current decisions reference immutable entry IDs with restrictive foreign keys. Ordinary duplicate imports still do not reparse or replace records. Full candidate revision matching and acceptance are the next slice: they must preserve logical entry identity for unambiguous unchanged evidence, surface uncertain matches, and never silently relocate decisions. The logical-entry helper currently returns the original entry ID; it is not a completed reparse implementation.

Corrections, issue acknowledgements, source revision acceptance, funding totals and contribution settlement remain in progress. No financial policy is implied by label assignments.

## References

* https://www.postgresql.org/docs/17/sql-createfunction.html
* https://www.postgresql.org/docs/17/sql-createview.html
* https://www.postgresql.org/docs/17/explicit-locking.html
* https://postgrest.org/en/stable/references/errors.html
