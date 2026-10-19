# Monthly reconciliation and contributions

This implements Linear FUR-8 and FUR-14. The operator separately approved the
hosted rollout of `0010_funding_totals` and `0011_contributions`; production is now
at `0011_contributions`. A protected backup, exact isolated restore, migration and
funding-flow rehearsal preceded the transactional live upgrade. Metadata, preserved
original data/PDF bytes, role-scoped funding operations, RLS/grants and managed API
anonymous denial were verified afterward. Rollback-only probes retained no synthetic
records. See [the rollout record](browser-workspace.md#operator-rollout-only-after-review-and-explicit-approval)
for private backup/audit locations. Future migrations still require explicit approval.
Public frontend hosting is separate and remains blocked by the repository plan.

## Using the workspace

1. Review statement evidence and assign budget Accounts independently of Categories.
2. Open **Reconciliation** and choose a statement month.
3. The account summary combines available cards, with a separate row per currency.
   It shows this month's net spending, contributions attributed to this month,
   this month's pending amount, and earlier months' pending amounts.
4. Expand **View cards** to inspect each card and original statement month.
   **Included entries** gives a paginated drill-down, independent of the transaction
   table's current page. Missing assignments, unknown facts, coverage warnings and
   competing sources remain visible. Use Statements or Imports to resolve them.
5. Open **Contributions** for the desired card/account/month. The original-month
   balances include earlier obligations for that same card/account/currency.
6. Enter a received date and optional note, then either record a positive partial
   amount or use **Settle in full**. This records contributions received; it does
   not pay the card bill or move money.
7. Inspect contribution history to see exactly which original months were covered.
   A January balance paid in February still settles January.
8. If later corrections affect a funded obligation, its month becomes **Needs
   review**. Provide a reason and confirm the revised balance before contributing
   again. Existing receipts and their original-month applications are not changed.

Other registered cards do not have to generate statements before an available
card can be reconciled or funded. Relevant unresolved issues on the affected card
still prevent misleading settlement. A summary is a view, not a shared cross-card
settlement obligation.

## Financial rules

- Use the bank's reviewed statement generation/issue date, falling back to its
  extracted statement date. Purchase, payment, upload and parser dates do not
  determine the reconciliation month.
- Include only published selected sources. Rejected or superseded evidence cannot
  duplicate totals. Pending competing sources are warnings, not extra spending.
- Exclude card repayments from new contribution requirements. Known debit spending,
  fees, interest and taxes increase the net; known non-payment credits, including
  refunds, reversals and cashback, decrease it. Unknown types/amounts/directions
  remain blockers rather than being guessed.
- Never combine currencies or invent exchange rates. Amounts remain PostgreSQL
  numeric/decimal strings and frontend BigInt cents, not floating-point totals.
- A negative monthly total is visible with no contribution due. Do not automatically
  offset it against another month or card.
- Apply partial/full contributions to the oldest positive outstanding obligation
  first within the same owner/card/account/currency, through the chosen month.
- Arrears retain their original month. They are not copied into a new monthly charge.
- Reject zero, negative, over-precise and excessive contributions. Record the
  received calendar date as entered, without shifting it through server time zones;
  it does not choose the obligation month. A full contribution covers only the
  currently reviewed outstanding amount.
- If a correction reduces an already funded obligation, show the resulting
  over-contribution credit. Do not silently move that credit to another obligation.
- Contributions are append-only; the browser does not edit or delete receipts.
  Automatic transfers, currency conversion, separate financial adjustments and
  split transaction allocations are not implemented.

## Minimal persistence

The original five evidence entities, account/category decisions and review history
remain unchanged. No monthly balance or copied obligation table is added.

`core/persistence/settlements.py` adds two sidecars:

- `contributions`: request UUID, owner/card/account/currency, through-month, exact
  amount, received date, optional note, actor, immutable original-month applications
  and the request snapshot used for idempotent retries. Applications contain the
  amount and evidence fingerprint acknowledged for each original month.
- `funding_confirmations`: append-only, reasoned acknowledgements of a changed
  original month's fingerprint. These do not edit earlier contributions.

Derived SQL views combine current reviewed obligations and receipt applications.
A group that disappears after a date/account/source correction remains visible if
it has contribution history, so money and changed-settlement warnings cannot vanish.

## API and concurrency contract

- `funding_totals`: complete, exact per-card/account/month/currency derived totals.
- `funding_groups`: derived net, received, outstanding, credit, source blocker and
  changed-history review flag. The client paginates every matching group, not just
  the visible transaction rows.
- `funding_attention`: competing, undated or coverage-unresolved statement sources.
- `funding_entries`: owner-scoped, paginated included-entry drill-down.
- `contributions`: owner-scoped receipt history; no direct table mutation grants.
- `funding_preview`: card/account/currency, through-month and captured owner context
  to coherent original-month balances plus a state token.
- `record_contribution`: request UUID, scope, decimal text amount or full-balance
  action, received date, note, expected state token and owner guard to one receipt.
  Exact retries return the same receipt even after the balance changes. Reusing an
  identifier with different input conflicts.
- `confirm_funding`: exact original month, through-month preview, reason, token and
  owner guard. Reconfirmation does not rewrite past received amounts.

Writes take the card lock and its statement-row locks in stable order before
checking the token. This coordinates with existing import, assignment, correction
and source-selection operations. Stale/concurrent requests cannot over-contribute.
Every mutation derives identity from the verified session; client owner context is
only a stale-session guard. Definer functions fix their search path, check ownership
and remove anonymous/public execution. All new sidecars use owner RLS and same-owner
card/account foreign keys. Browser clients have no receipt update/delete privileges.

The UI retains an uncertain request identifier for a safe retry and prevents a new
request while that result is uncertain. On reload, inspect receipt history before
repeating a payment entry. A received server rejection preserves an editable draft.

## Reconciliation query performance

A multi-account production summary exposed repeated evaluation of the nested
reviewed-evidence views. This could exceed the managed authenticated-role
8-second statement limit even though migrations and grants were correct.

The prepared `0012_funding_query_plan` migration evaluates owner-scoped obligations,
applications and confirmations once per query using materialized CTEs, then reuses
them for the account/month joins. It does not create cached balance tables, alter
financial calculations or raise database timeouts. Existing RLS and grants remain
in force; verified-owner filtering also bounds work inside definer operations.

The optimized query passed a read-only test against the live data in approximately
1.1 seconds, where the old query exceeded 15 seconds. On a password-protected
restored copy, old and new reconciliation rows and fingerprints matched exactly,
and the optimized query completed under the real 8-second budget. Regression
coverage includes several budget accounts, the full managed API list request and
the query materialization fences. The frontend identifies SQLSTATE 57014 as a query
timeout instead of incorrectly suggesting a missing upgrade or bad connection.

This performance migration is tested but not yet approved or applied to production.
The hosted revision remains `0011_contributions` until a separate rollout approval.

## Verification and rollout

Frontend unit tests and actual isolated Auth/API/browser tests cover exact values,
more than one transaction page, separate cards/currencies, reviewed month dates,
refunds, repayments, negative months, unassigned data, competing/empty sources,
partial/full receipts, original-month attribution, concurrency, retries, corrections,
reconfirmation, persistence after reload and desktop/mobile rendering. Migration
round trips, metadata drift, default-deny access and native backup/restore remain
part of the disposable PostgreSQL suite.

Run the repository's frontend tests/build and Python suites, plus the isolated
Supabase suite including `tests.test_reconciliation_http`,
`tests.test_settlements_http` and `tests.test_funding_e2e`. See
[browser setup and verification](browser-workspace.md).

App-schema backups automatically include both new sidecars and API objects, but
omit Supabase Auth and ACLs. Restore into a fresh isolated database, verify original
rows and receipt applications, and reapply reviewed browser privileges only after
review. Downgrade refuses to discard existing contribution or confirmation history.
No new migration is applied to production by running implementation tests. GitHub
Pages hosting remains blocked by the current private-repository plan entitlement.

## Sources

- https://www.postgresql.org/docs/17/explicit-locking.html
- https://www.postgresql.org/docs/17/functions-aggregate.html
- https://www.postgresql.org/docs/17/functions-json.html
- https://supabase.com/docs/reference/javascript/rpc
- https://supabase.com/docs/guides/database/postgres/row-level-security
