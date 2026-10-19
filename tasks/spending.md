# Spending by category and trip

Approved direction: the interactive Spending mockup in this chat. Add Spending beside Summary; preserve account reconciliation. A transaction has one optional trip/group independently of account and category.

## Ordered slices

1. Persist groups and assignments using owner-scoped sidecars and guarded RPCs. Names can be created, renamed and archived. Group assignments follow logical entry identity across parser revisions. Batch changes are atomic, reject stale versions, and never alter financial facts or account/category decisions. Verify migrations, RLS, cross-owner denial, stale batches, source replacement and metadata drift with disposable databases.
2. Add exact spending calculations and paginated API loading. Use selected sources and reviewed transaction dates; exclude repayments, retain unknown dates in all-date views, and show incomplete/review flags. Keep currencies separate. Verify totals, refunds, more-than-one-page loads, errors and cancellation.
3. Build responsive Spending navigation, category/trip views, period controls, totals, breakdown filters, transaction lists, group management and batch add/move/remove actions. Demo changes stay memory-only. Verify component flows, existing suites, production build and desktop/mobile browser checks.
4. Add a Statements entry action for trip assignment and Summary category shortcuts. Verify saved membership survives navigation/reload and account/category/reconciliation values stay unchanged. Document usage and migration rollout.

## Contracts

- `spending_groups`: id, name, is_archived, version; `save_spending_group` follows existing label RPC conventions and requires the captured owner.
- `spending_entries`: selected reviewed entries plus group_id, group_name and group_version. Reads use stable ordered pagination.
- `assign_spending_group`: captured owner, optional destination group, and at most 50 `{id, version}` entry references. Entire batch succeeds or fails; null destination removes membership. Independent assignment versions protect concurrent changes.
- No hosted migration or deployment during implementation. Migration 0015 is verified locally and delivered for the existing reviewed rollout process.

## Checklist

- [x] Persistence and migration verified.
- [x] Spending calculation and loading verified.
- [x] Responsive page and group management verified.
- [x] Statements and Summary integration verified.
- [x] Full checks, browser validation and usage documentation complete.

## Verification evidence

- Full Python suite with disposable PostgreSQL: 297 tests, 72 environment/private-data opt-outs, no failures. Migration upgrade/downgrade round trips, metadata drift, idempotence and refusal to discard saved groups pass.
- Frontend suite: 20 files and 67 tests passed before the final currency regression case; the three focused Spending cases and Summary integration checks pass afterward. Production TypeScript/Vite build and Prettier checks pass.
- Actual Auth/API: 24 Spending, reconciliation, contribution and revision tests pass. Spending checks include stale versions, atomic batches, foreign owners, anonymous access, archival, repayment exclusion and logical identity after replacement.
- Actual authenticated Chromium: cross-card grouping, refunds, category drilldown, transaction month selection, reload persistence and per-entry membership changes pass at 1440px, 390px and 320px without document overflow or page errors.
- Separate friendly-description work was preserved and its Spending projection integration retained. Existing edits were not committed as part of this task.
- Hosted schema remains unchanged. Follow the reviewed rollout process for 0015 before signed-in use.
