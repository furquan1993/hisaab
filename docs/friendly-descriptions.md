# Friendly transaction descriptions

Expand a transaction and choose **Edit description** to add a personal description
of up to 500 characters, such as “Desk lamp from Amazon”. It appears as the main
transaction text, with the bank's original description underneath. Clearing the
field restores the reviewed description, falling back to the extracted description.
**Search descriptions** matches original, reviewed and friendly descriptions across
the complete date-filtered result set, including entries beyond the current page.
Funding drill-downs also display friendly descriptions. Synthetic demo edits last
only for that demo session.

Descriptions belong to individual logical transactions. They do not rename other
purchases from the same merchant. Accepted reparses retain them through existing
logical identity mappings; unmatched new transactions start without a description.

## Storage and API

Migration `0016_friendly_descriptions` follows `0015_spending_groups` from the
parallel spending-explorer work. It adds one owner-scoped, append-only table,
`hisaab.entry_descriptions`. Each snapshot records the logical entry, independent
version, nullable description (null records a clear), timestamp and verified actor.
No existing records are backfilled or rewritten.

`entries` exposes `friendly_description` and `friendly_description_version`.
`funding_entries` exposes the description; `spending_entries` exposes both.
`save_friendly_description(p_entry_id, p_expected_version, p_description)` trims
text and treats blank/null as a clear. Repeating the current value is a no-op.
It uses the selected-source statement lock and checks the description version;
stale versions or superseded/candidate sources return HTTP 409. Unavailable entries
return 404 and invalid lengths/versions return 422. The browser retains failed drafts.
Only authenticated, mapped owners can save their own selected transactions.
Browser roles have owner-filtered read access and cannot directly mutate snapshots.

Friendly descriptions do not change evidence, reviewed facts, decision versions,
account/category assignments, assignment learning, review readiness, reconciliation
fingerprints, contributions or totals. This independence is why descriptions use a
separate record rather than the existing financial decision version.

## Verification and rollout

Local synthetic tests cover save/change/clear, no-op saves, independent financial
snapshots, audit actors, owner isolation, invalid/stale writes, accepted reparses,
old-source rejection, search, and desktop/mobile reload persistence. Migration
checks cover schema drift, upgrade/downgrade round trips and refusal to discard
populated description history. Downgrade preserves the additive API columns as
empty placeholders so dependent views retain their definitions and grants.

The approved hosted migration completed on 2026-10-19, upgrading
`0015_spending_groups` to `0016_friendly_descriptions`. A fresh owner-private backup
was checksummed, restored into a password-protected isolated PostgreSQL container,
and used to rehearse the exact migration. Existing records, PDFs, assignments,
learning history and financial view results were verified unchanged. Authenticated
save/clear/conflict checks ran in transactions that were rolled back, leaving no
probe records. The private recovery manifest is retained under Git-ignored `data/`.

Frontend publication uses the existing owner-private
[Hisaab site](https://hisaab-spending.fur-ahmed.chatgpt.site), preserving its audience
and existing app login. Future migrations require their own approved backup,
restore rehearsal and rollout. Description history cannot be silently discarded
by downgrade.

Patterns follow PostgreSQL's [view replacement and invoker security contract](https://www.postgresql.org/docs/17/sql-createview.html)
and [security-definer function guidance](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
