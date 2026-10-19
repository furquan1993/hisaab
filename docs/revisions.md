# Safe parser revisions

Implementation is not deployed to the hosted project. New migrations and permissions require review and a separately approved rollout.

Normal PDF import remains duplicate-safe: the same bytes return an existing import without decryption or reparsing. Explicitly request a new parser candidate from a retained original:

```sh
uv run python -m core reparse-import --owner OWNER_UUID --import-id IMPORT_UUID
```

The command uses hidden terminal input only if the PDF needs a password, prints IDs/counts rather than financial rows, and returns review exit code 3. It never selects the candidate automatically. Existing JSON output contracts are retained.

## Evidence and identity

A parser revision is a new Import extraction with new immutable Entry evidence rows. It references the original file-owning Import using `source_import_id`; composite constraints enforce the same owner, card, bill and SHA-256. Borrowed payloads are not duplicated and are not falsely marked deleted. Download/export follows the verified original reference and still checks byte size and SHA-256. Deleted originals are not restored by duplicate imports.

A published logical entry keeps its original root UUID and decision record. `logical_entry_id` is distinct from the current extraction's source-evidence `id`. New immutable `entry_links` bind accepted evidence to these roots, with at most one occurrence of a logical identity per extraction.

An automatic match requires identical extracted facts, raw text, page/bounds and issues, a unique full-provenance fingerprint on each side, and the same sequence position. Similar purchases are not deduplicated. Reordering, ambiguous duplicate provenance, splits, merges and changed rows need explicit review. Mapping a changed row retains its logical decisions rather than moving or deleting records; source-bound corrections need separate revalidation in the review layer.

## Atomic acceptance

A pending comparison records its base source, complete evidence hashes and automatic matches. Acceptance locks the bill and comparison, rejects changed published sources or evidence, requires explicit decisions for every uncertain candidate and acknowledgement of every removed published row, and records a reason and verified actor. A logical root cannot be duplicated across new rows. Existing published evidence cannot be rebound; propose a fresh parser version instead.

Failed or unaccepted revisions do not change published facts or allocations. A late failure rolls back identity links, selection and revision status together. Repeated acceptance of the current accepted revision is a no-op. Superseded and rejected sources stay available through explicit history/evidence views, but are excluded from ordinary date/review queries.

The managed mutation API derives ownership from the verified session, not a caller-supplied owner. Private operator helpers are not executable by browser roles. Original bytes remain available only through explicit owner-checked download/export.

## Verification

`tests/test_revisions.py` covers unchanged identity/decision preservation, reorder conflicts and explicit mappings, removed-row decisions, stale comparisons, foreign owners, failure rollback, retained original bytes and no-parse duplicate retries. `tests/test_revision_http.py` verifies actual JWT/API acceptance, preserved labels, archived evidence, source downloads and isolation. No live statements are used by these tests.
