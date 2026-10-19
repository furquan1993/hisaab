# Implementation checkpoints

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
