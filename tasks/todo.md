# Implementation checkpoints

Authenticated import redesign:
- [x] Atomic authenticated import RPC and duplicate preflight; real Auth/API
      tests cover isolation, malformed rollback, encrypted bytes and concurrent retries.
- [x] Public project config and CLI email/password login; in-memory sessions,
      refresh, local logout, redacted failures and legacy operator compatibility.
- [x] UI commands and onboarding docs; 93 frontend tests, build and formatting;
      full Python/PostgreSQL/Auth suite passed (347 tests, 16 opt-in skips).
      A stale disposable reconciliation view was restored to committed 0016 SQL
      before the passing run; no unrelated source change was needed.
- [x] Implementation committed to main as `df9e865`; all GitHub workflows passed.
- [x] Separately authorized hosted rollout completed on 2026-10-19 from `0019`
      to `0020_authenticated_imports` after fresh backup, exact restore and
      rehearsal. Live role-scoped smoke checks rolled back all synthetic writes;
      data/PDF/view fingerprints and RLS/grants were preserved. Managed API
      endpoint discovery and anonymous denial passed. Private recovery evidence:
      `data/migration-rollout/authenticated-imports-verified-backup.json`.

Current Spending implementation: [spending.md](spending.md).

Live feature status belongs to Linear FUR-8 and FUR-14. This is the execution checklist for the approved combined implementation.

- [x] Complete owner-scoped reconciliation reads and focused tests.
- [x] Add minimal contribution/confirmation sidecars and guarded immutable writes.
- [x] Verify partial/full contributions, original-month attribution, corrections, races and recovery.
- [x] Add monthly summary, card drill-down, contribution history and actions.
- [x] Verify synthetic demo and authenticated desktop/mobile browser flows.
- [x] Run full suites, formatting, build and metadata checks.
- [x] Update usage/schema documentation and Linear with verification evidence.
- [x] Obtain separate approval and complete the protected hosted rollout through `0011_contributions`, including restore/rehearsal, exact metadata/data checks, rollback-only live funding verification and managed API anonymous denial.

Public frontend hosting remains blocked by the current private-repository Pages plan; the database rollout does not resolve that separate gate.
