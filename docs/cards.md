# Cards

Open **Cards** in the workspace sidebar. Enter a card name, choose HDFC Bank,
SBI or YES Bank, optionally enter the last four digits, then select **Add card**.
Only the last four digits are stored; the form never needs the full number.

Select **Edit** beside a saved card to update it, then **Save changes**.
**Cancel** discards the draft. The bank can be corrected before statements exist;
after an import it is fixed so existing statements retain their bank identity.
Names and last four digits remain editable. Renaming a card updates its display
name in statement and reconciliation views without changing transactions.

Saved cards show their ID for the existing statement-import workflow. Adding a
card does not import a statement. Demo cards and edits last only for the current
synthetic demo session.

## API and rollout

Migration `0018_card_management` adds an owner-filtered `hisaab_api.cards` invoker
view and `save_card` RPC, using the existing authenticated-owner mapping and RLS.
The RPC accepts `p_expected_owner`, `p_label`, `p_bank`, `p_last_four`, `p_id` and
`p_expected_version`. New cards use null ID and version 0; edits use the current
ID/version. It returns ID, label, bank, last_four, version and has_statements.
Stale saves and bank changes after imports return 409; unavailable cards return
404 and invalid fields return 422. Unmapped and anonymous callers cannot write.
Browser clients cannot mutate the card table directly. Card-row locks serialize
edits with statement imports. Lists use ordered pages of 100.

The approved database rollout completed on 2026-10-19 from
`0017_account_deletion` to `0018_card_management`. A fresh private backup was
checksummed, restored into a password-protected temporary local PostgreSQL
database, and used to rehearse the exact migration. Existing table contents,
financial views and original PDF bytes were verified unchanged. Authenticated
card creation/editing, stale saves, bank locks and owner isolation passed in
rolled-back transactions, retaining no synthetic records. Private recovery
evidence is in Git-ignored `data/migration-rollout/cards-verified-backup.json`.

The frontend release is separate. Future database rollouts follow the
backup/rehearsal procedure in [browser workspace](browser-workspace.md).

Sources: [PostgreSQL function security](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY),
[Supabase RLS and invoker views](https://supabase.com/docs/guides/database/postgres/row-level-security).
