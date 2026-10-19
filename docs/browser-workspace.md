# Static statement-review workspace

React 19.3.1, TypeScript 7.0.2 and Vite 8.3.4 serve static assets only.
Supabase JS 2.118.0 handles managed email/password Auth and the managed Data API.
There is no custom data server, SSR, browser parser or money transfer. The initial hosted release was read-only. The approved hosted database
rollout is now complete through `0014_statement_balances`, supporting independent
Account/Category management, versioned assignments, reasoned entry and statement
review, explicit parser-revision comparison, monthly summaries, per-card contributions,
and separate printed statement amounts due. Future database changes still
require a separately reviewed and approved rollout.

## Try the synthetic demo now

From the repository root:

```sh
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:5173/hisaab/ and choose **Explore synthetic demo**.
No Auth account, database migration or financial upload is required for this
mode. Every demo row is explicitly invented in `web/src/demo.ts`; there is no
automatic fallback to demo rows after a live-query failure.

In Statements, click a compact entry row or use its keyboard-accessible disclosure
button to expand it. View, Assign and Review open directly beneath that row;
only one row and one panel are open at a time. Closing a panel returns focus to
its action, while saving returns focus to the row without jumping down the page.
Changing filters, pages or workspace sections closes the expansion. Source facts
and existing save/version checks are unchanged.

The developer server serves static application assets, not financial data.
Production needs only the static `web/dist` directory. Node 24 is used in CI.

## Monthly reconciliation increment

The independent [Spending explorer](spending.md) adds category and trip/group
views alongside reconciliation. Trip membership does not alter an entry's
category or funding account. Migration `0015_spending_groups` was approved and
deployed on 2026-10-19 after a verified backup restore and rehearsal. The
[owner-private app](https://hisaab-spending.fur-ahmed.chatgpt.site) uses the existing
app login. GitHub Pages is unavailable on the current private-repository plan.

The **Reconciliation** section combines budget-account spending across available
cards by statement month and currency, with per-card full/partial contributions,
original-month arrears, receipt history and reasoned reconfirmation after corrections.
No all-cards readiness gate is imposed. Summary/card/entry drill-downs and contribution
panels are inline. See [financial rules, data models and API contracts](reconciliation.md).

Revisions `0010_funding_totals` and `0011_contributions` were separately approved
and deployed after the protected recovery/rehearsal checks below. Do not treat
implementation, a green test suite or a frontend rebuild as approval for future
hosted migrations. Public Pages hosting remains blocked by the repository plan.

## Public browser configuration

Copy `web/.env.example` to `web/.env.local`, then fill:

```dotenv
VITE_SUPABASE_URL=https://PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
```

The URL must be the **project root**, without an API path such as /rest/v1.
The publishable key is intentionally public. A legacy anon key is also
supported, but secret/service-role keys and credential-bearing URLs are rejected
before a production bundle can be emitted. Never put database settings, Auth
passwords, signing keys or service-role keys in Vite environment variables.
The private Python TOML is not imported by the browser app.

The example is tracked; local values, node_modules and dist are ignored.
Restart the dev/build command after changing configuration. Public settings are
build-time configuration, not a way to change a deployed bundle remotely.

## Operator rollout: only after review and explicit approval

Implementation does **not** deploy migrations, grant hosted access or load
real financial records automatically. The user explicitly approved all pending
migrations, and the hosted database was upgraded from `0003_browser_queries` to
`0009_reasoned_review` after the following checks:

- Migration review, disposable PostgreSQL tests, real isolated Auth/API/browser
  tests, frontend tests and a production build passed.
- A private app-schema backup was checksummed and restored into a fresh isolated
  PostgreSQL 17 database. All original rows and PDF bytes matched.
- All six pending migrations passed rehearsal on that restored copy, with original
  data unchanged and no ORM metadata drift.
- The live upgrade committed transactionally. Revision, metadata, original-data
  fingerprints, PDF integrity, RLS and API grants were verified.
- Authenticated Account and Category creation/read checks passed in a transaction
  that was rolled back, leaving no test labels in production.

The private backup is `data/exports/run-csps1pet/database.dump`; its adjacent
`manifest.json` records its checksum and source revision. The private verification
record is `data/migration-rollout/verified-backup.json`. The archive is not encrypted
and does not contain Supabase Auth; the backup boundary below still applies.

The subsequent, separately approved funding rollout upgraded the database from
`0009_reasoned_review` to `0011_contributions`. A fresh backup was checksummed and
restored into a password-protected isolated PostgreSQL database. All existing
application rows, labels, review history and PDF bytes matched. Both migrations,
metadata/grant checks and rollback-only partial/full contribution, original-month
allocation and correction/reconfirmation checks passed on that copy before the
transactional live upgrade. The same role-scoped checks passed in production and
retained no synthetic records. All earlier rows remained unchanged. The managed
Data API loaded the new views/RPC and denied anonymous access.

The funding pre-rollout backup is `data/exports/run-qfi0uir5/database.dump`;
`data/exports/run-l791hmo5/database.dump` is the checksummed post-rollout backup.
Each has an adjacent revision/checksum manifest. The private audit record is
`data/migration-rollout/funding-verified-backup.json`. These are local, owner-only,
unencrypted app-schema backups, not Auth backups or off-device recovery copies.

Preserve the approved target for future deployments. Back up, restore-check and
obtain explicit rollout approval after code review for future migrations; a
successful synthetic demo alone is not deployment approval.

1. In Supabase, disable public signups and anonymous sign-ins. Keep the **email
   provider enabled** so existing users can sign in. Create the initial user
   administratively and confirm its email. Keep its password private.
2. Inspect the migration SQL and make the backup/deployment decision.
   Inspect `uv run alembic current` privately and apply only the explicitly approved
   target revision, not an unreviewed moving head. Verify migration drift afterward.
   Never edit deployed revisions or treat this document as rollout authorization.
3. Use `uv run python -m core owners-list`. Reuse the intended existing owner,
   or create one once with `uv run python -m core owner-create "Primary"`.
4. Bind the existing owner through the trusted CLI:
   `uv run python -m core owner-auth-link OWNER_UUID AUTH_USER_UUID`.
   This verifies the Auth subject exists in this same database, rejects an
   occupied subject or implicit replacement, and is idempotent for the same link.
   There is no browser owner-claim/signup endpoint.
5. In Supabase Data API settings, add **hisaab_api** to Exposed schemas.
   **Do not expose hisaab.** Existing unrelated public endpoints need not be
   changed. The app requests the explicit API schema.
6. Open the app and sign in with the Auth email/password, not the database
   password. A signed-in but unmapped user gets a setup error and no data.
7. For real statements, complete FUR-20 separately before the first controlled
   import. Browser PDF upload/parsing is not implemented. The normal import CLI
   remains the ingestion path.

To revoke an owner's app-data access immediately, including existing JWTs:

```sh
uv run python -m core owner-auth-unlink OWNER_UUID
```

Unlink before deleting/replacing an Auth user. Supabase-issued access tokens
otherwise have their normal lifetime; signing out this tab is not a promise
to revoke all access tokens on other devices instantly.

## Data and access contract

- Stable financial Owner IDs are not Auth subjects. An optional unique
  `Owner.auth_user_id` binds one trusted login to one owner, without an
  `auth.users` foreign key or destructive Auth-user cascade.
- PostgREST validates JWTs. The policy helper reads the verified transaction
  claim, accepts only the authenticated role, and takes no client owner argument.
  Its narrow definer execution avoids recursive Owner RLS; its search path is
  fixed and every application object is qualified.
- All evidence and decision tables have owner-scoped read policies. Browser clients
  have no direct table mutations; narrowly validated, version-checked mutation
  functions save decisions and audit records separately. There are no original-fact,
  PDF or identity writes. Anonymous and unmapped
  clients cannot read records. Platform default grants are explicitly removed,
  including from the application's public migration ledger.
- Invoker views `profile`, `entries` and `entry_evidence` respect underlying
  RLS. Normal queries cannot fetch PDF bytes or Auth-subject mappings.
- `original_pdf(p_import_id)` is an explicit, read-only, owner-checked definer
  operation. It verifies SHA-256 before returning base64; the browser verifies
  again before offering the unchanged file. Deleted originals return unavailable.
- Entry money crosses the API as decimal **strings** and is displayed through
  BigInt-based grouping, never floating-point conversion. Null facts stay null.
- Statement-date ranges include all selected-source rows of matching bills.
  Original extracted dates remain the default filter basis. An explicit Reviewed
  dates option filters on verified corrections with source-value fallback. Corrected
  values are shown alongside originals. Bounds are inclusive and date-only strings
  are never shifted through UTC conversions.
- The separate all-date Needs review queue includes issues, missing dates and
  competing imports. Candidates never silently enter selected-source views.
  Repeated purchases remain distinct rows.
- Requests use deterministic ordering, 50-row pages and explicit total counts.
  Loading/errors do not reuse misleading demo or previous-query results.
- The initial live range is the latest available statement month; with no dated
  selected entries it uses the current local calendar month. Demo starts January
  2026 only as an invented example; no live reconciliation period is fixed to it.
  Statements belong to the calendar month in which the bank generated/issued them,
  never purchase, payment-due, upload or parser-run months.
- Tokens are tab-scoped in sessionStorage; financial rows are not persisted in
  browser storage. Refresh/expiry/sign-out discard stale view state. Text is
  React-escaped; no financial telemetry, remote fonts or third-party assets.
  Use a trusted browser/device and review other applications on the same Pages
  origin; a repository path is not a separate browser security origin.

## GitHub Pages

The repository is private. GitHub Pages requires an eligible plan for private
repositories. Do not make it public merely to enable hosting without a separate
source/privacy review. The static demo remains usable locally in the meantime.

After merge, hosting approval and backend rollout:

1. Enable GitHub Pages with **GitHub Actions** as the publishing source.
2. Set repository Actions **variables** (not privileged secrets):
   `HISAAB_SUPABASE_URL` and `HISAAB_SUPABASE_PUBLISHABLE_KEY`.
3. Run **Deploy static workspace** manually. It builds, checks public
   configuration and deploys only `web/dist`, never Python config or data/.
4. Use the deployed /hisaab/ URL. Configure the exact site URL in Supabase Auth
   for any future confirmation/reset redirects. Current password sign-in does
   not require an email per login or a custom callback server.
5. Privately verify login, both views, evidence, original download and sign-out.
   Pages deployment alone is not proof of live database isolation.

Built-in email delivery and free-project inactivity pausing have separate
limits. No paid email service is assumed; password recovery delivery is not
implemented as part of this preview.

## Backup and restore boundary

The app-schema backup now includes hisaab_api when present and records the schema
scope list in the manifest. Original financial IDs, source bytes, the optional
Auth mapping, views and helper functions recover without copying Supabase's
managed auth schema. Auth users/passwords/signing keys are **not** part of this
app backup.

Archives intentionally omit ACLs/ownership. A fresh restore must remain
browser-denied until an operator re-applies the reviewed grants for
the approved target schema, verifies RLS through the actual API, and reviews/relinks Auth subjects
for the target project. Do not blindly assume an old provider UUID identifies
the intended person in a new project. FUR-20 must validate this operational
rollout before relying on a production backup.

## Verification

Python tests demonstrate failing identity/policy/query/link tests before their
implementation. The isolated suite creates real confirmed synthetic Auth users,
signs in through GoTrue, and tests actual PostgREST JWT requests rather than
merely mocking SQL roles.

```sh
cd web
npm ci
npm test
npm run build
npx playwright install chromium
cd ..
web/node_modules/.bin/supabase start -x realtime,storage-api,imgproxy,mailpit,postgres-meta,studio,edge-runtime,logflare,vector,supavisor
umask 077
web/node_modules/.bin/supabase status -o json > /tmp/hisaab-supabase-status.json
HISAAB_SUPABASE_TESTS=1 HISAAB_BROWSER_TESTS=1 \
  HISAAB_SUPABASE_STATUS_FILE=/tmp/hisaab-supabase-status.json \
  uv run python -m unittest tests.test_browser_http tests.test_decisions_http tests.test_review tests.test_revision_http tests.test_reconciliation_http tests.test_settlements_http tests.test_browser_e2e tests.test_funding_e2e -v
```

The status file contains **disposable development secrets**; never upload it or
the startup log. The fixture refuses other API endpoints/container identities,
does not read private production config, and deletes only its own synthetic
records. Run the existing disposable PostgreSQL suite for migration round trips,
native recovery and parser/persistence regressions. CI runs both jobs separately.

## Official sources

- https://supabase.com/docs/guides/database/postgres/row-level-security
- https://supabase.com/docs/guides/api/using-custom-schemas
- https://supabase.com/docs/guides/api/api-keys
- https://supabase.com/docs/guides/auth/passwords
- https://supabase.com/docs/guides/auth/auth-smtp
- https://supabase.com/docs/guides/local-development/cli/config
- https://postgrest.org/en/stable/references/transactions.html
- https://www.postgresql.org/docs/17/sql-createfunction.html
- https://www.postgresql.org/docs/17/functions-binarystring.html
- https://react.dev/reference/react-dom/client/createRoot
- https://vite.dev/guide/env-and-mode
- https://vite.dev/guide/static-deploy
- https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages


### Filter statement transactions

In **Statements**, use **Account** and **Category** beside **Search descriptions**
to narrow the transaction list. Choose a named label (including archived labels),
**Unassigned**, or **All accounts / All categories** to remove that filter.
Filters combine with each other, description search and the selected date view.
They apply before pagination, so **Matching entries** counts every matching row.
Changing either filter returns to the first page. Changing an entry's assignment
while filtering refreshes the list so entries that no longer match disappear.


### Bulk account and category updates

In **Statements**, tick transaction checkboxes or use **Select all on this page**.
Choose **Account for selected transactions** and **Set account**, or choose
**Category for selected transactions** and **Set category**. **Unassigned** clears
that field. Only active labels can be assigned. Each action preserves the other
assignment and trip membership, and teaches the same future matches as an
individual edit.

Selection covers the current page (up to 50) and clears when filters, dates,
sorting or pages change. Candidate sources cannot be selected. Saves use each
transaction's expected version and run individually; a failure stops the batch.
The result reports confirmed updates, which remain saved. Refresh before
retrying an unconfirmed save, then select the remaining transactions again.

## Friendly transaction descriptions

The separately approved `0016_friendly_descriptions` rollout completed on 2026-10-19
after a fresh private backup and verified restore rehearsal. Friendly descriptions
use independent versions and preserve financial decisions and settlement checks.
See [usage and verification](friendly-descriptions.md).
