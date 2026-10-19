# Monthly reconciliation and card-scoped contributions

Linear FUR-8 and FUR-14 remain the task/status source. The operator approved implementing the summary and settlement workflow together. This plan supersedes the earlier combined-settlement and all-cards completeness proposals.

## Contract and boundaries

- Derive obligations from selected-source, reviewed entries using the bank statement month, never purchase or payment dates. Preserve every original fact.
- Aggregate the monthly summary by account and currency across available cards. Drill down to card/account/currency/month groups. Exclude card repayments; debit spending, fees, taxes and interest increase requirements; confirmed credits reduce them. Unknown facts remain explicit blockers, not invented amounts.
- Refunds/reversals reduce the month where posted. Retain negative net totals with zero required contribution and no automatic negative carryover.
- Record full or partial contributions within one owner/card/account/currency. Apply them oldest outstanding month first through the chosen month. Each application keeps its original obligation month. Do not copy arrears into new spending.
- Derive remaining balances and over-contribution credits. Never automatically move credits between months or currencies. Reject contributions exceeding outstanding obligations.
- Preserve contribution history after corrections. Fingerprint affected obligations and require an explicit reasoned confirmation before new contributions against changed history. Block only relevant card data, never absent statements from unrelated cards.
- No transfers, currency conversion, transaction splitting, historical workbook import, automatic suggestions, or new hosting setup. New hosted migrations require a separate reviewed rollout.

## Ordered increments

### 1. Read-only reconciliation contract

Files: migration SQL, migration revision, focused HTTP tests.
Acceptance: complete owner-scoped aggregates independent of transaction pagination, exact decimal strings, separate currencies, selected sources only, visible unresolved and unassigned groups. No obligation tables or copied monthly balances.
Verification: disposable Auth/API tests for multi-card totals, more than 50 entries, credits/repayments, corrected statement dates, candidates and foreign users.

### 2. Contribution ledger and guarded writes

Files: persistence sidecars, migration revision/SQL, metadata registration, focused settlement tests.
Acceptance: immutable receipts with server-calculated original-month applications; idempotent request IDs; exact positive decimal validation; serializable card-scoped operation through row locks; stale-state checks; preserved receipts and explicit confirmations after corrections. Native backup includes the new sidecars.
Verification: actual HTTP tests for partial/full, oldest-first allocation, reload, overpayment, stale retries, race safety, reviewed changes and owner isolation; migration drift and recovery tests.

### 3. Monthly summary and settlement interface

Files: reconciliation domain/client, reconciliation component, workspace navigation, styles.
Acceptance: monthly combined account/currency table, card/month drill-down, visible arrears and credits, contribution history, partial/full actions, reasoned reconfirmation. Keep exact money in BigInt, validate responses, avoid first-page totals and live-to-demo fallback. Demo changes are memory-only.
Verification: frontend unit tests and production build after each UI slice.

### 4. Full-flow verification and documentation

Files: browser smoke, isolated browser runner/CI, user and schema guides.
Acceptance: actual authenticated flow across two months, contribution persistence on reload, correction/reconfirmation and original-month attribution; desktop/mobile usability; existing entry review remains intact. Update Linear with evidence and remaining rollout/hosting gates, not an unsupported production-ready claim.
Verification: full Python and frontend suites, actual Auth/API/browser suites, formatting, build, metadata check and synthetic restore.

## API outline

- `funding_groups`: paginated owner-scoped read view. Stable group dimensions, signed net, received, outstanding and credit as decimal strings; financial fingerprint; blocker and review flags.
- `contributions`: paginated owner-scoped receipt history including applications and actor/date/note. No direct browser mutations.
- `funding_preview`: captured owner context, card/account/currency and through-month to a coherent current-state token and original-month balances.
- `record_contribution`: client UUID idempotency key, expected preview token, owner guard, date, decimal text amount or full-balance action, optional note. Returns the immutable receipt. Reusing an ID with different input conflicts.
- `confirm_funding`: expected preview token, exact affected month and reason. Appends confirmation without editing prior contributions.
- Errors follow existing PT404/PT409/PT422 and access-denied conventions. Definer functions fix their search path and explicitly verify session ownership. All sidecars use owner RLS and same-owner foreign keys.

## Risks

Contribution allocation races with existing review and import operations. Serialize by card and lock its statement rows in stable order before checking the state token. History must retain vanished groups after account or date corrections so over-contributions and stale settlement claims cannot disappear. Real workbook values never enter fixtures, logs or committed documents.
