# Statement loading

For an existing hosted workspace, start with the
[first-time import guide](import-your-first-statement.md). It explains local
setup, database credentials, and the commands to run for each new PDF. The
sections below are the operator and implementation reference. Ordinary
`import-pdf` commands now sign in with the UI account and call authenticated
APIs; only an explicit `--config` selects direct database imports.

The approved hosted rollout of `0020_authenticated_imports` completed on
2026-10-19 from `0019_transaction_contributions`. A fresh checksummed app-schema
backup was restored into a password-protected disposable PostgreSQL instance,
verified against all original rows and PDF bytes, and used to rehearse the exact
migration. The live migration committed transactionally. Role-scoped import,
duplicate, candidate, encrypted-original, malformed-rollback and owner-isolation
checks passed with all synthetic writes rolled back. Existing data, views,
permissions and RLS were preserved, and the managed API loaded both new endpoints
and denied anonymous calls. Private recovery evidence is Git-ignored at
`data/migration-rollout/authenticated-imports-verified-backup.json`.

This milestone adds a trusted single-user CLI backed by the existing five-entity
schema. No new schema migration is required. The initial schema was deployed
to Supabase on 2026-10-18; no private statements were uploaded during development.

## Setup and first controlled load

Use the owner-only, Git-ignored `config.local.toml` described in the
[connection guide](../README.md#private-database-connection). Never put passwords
or connection strings on command lines.

After reviewing/merging this feature and explicitly deciding to load real data:

1. Verify connectivity and the applied migration.
2. Establish a backup before the first financial load.
3. Register a data owner and card.
4. Import one original statement and compare it with the source locally.
5. Reimport renamed identical bytes and verify the same IDs and counts.
6. Only then import a batch.

```sh
uv run python -m core db-check
uv run alembic current
uv run python -m core database-backup
uv run python -m core owner-create "Primary"
uv run python -m core owners-list
uv run python -m core card-create --owner OWNER_UUID --bank hdfc --label "Regalia"
uv run python -m core cards-list --owner OWNER_UUID
uv run python -m core import-pdf --config config.local.toml --owner OWNER_UUID --card CARD_UUID data/statement.pdf
uv run python -m core imports-list --owner OWNER_UUID --card CARD_UUID
```

Replace UUID placeholders with returned IDs. Supported bank identifiers are
`hdfc`, `sbi`, and `yes_bank`. The optional card `last_four` is an identifier
aid, not a primary key. Select the physical card explicitly: a bank match alone
does not prove that the PDF belongs to a particular card number.

Owner registration creates a data profile, not an authenticated application
login. Privileged direct database credentials can bypass RLS. This does not
enable a second independent user or justify sharing those credentials.

## Original bytes, not reconstructed pages

The importer reads the original file once into immutable bytes. It extracts
facts from that same snapshot and stores the original bytes unchanged.
It does not rebuild pages, strip encryption, or persist a decrypted PDF copy.

Original SHA-256, original byte length, parser/extractor/schema versions, every
entry, exact Decimal amounts, null facts, raw provenance, and review issues are
preserved. PDF encryption remains intact; PDF passwords remain in memory only.

Cloud-import inputs must resolve inside this project's Git-ignored `data/`
directory. Copy a source there explicitly before importing. Paths and symlinks
escaping that root, special files, invalid PDFs, and probe JSON are rejected.
Local-only parse commands retain their existing behavior.

New encrypted statements use hidden terminal password entry. A noninteractive
call without a usable password fails before writes. There is no password flag,
saved PDF-password store, or automatic reading of test credential files.
A duplicate encrypted PDF needs no password because its fingerprint is already
known.

## Import outcomes

Each PDF is one atomic transaction; a batch is not one transaction. Earlier
successful files survive a later failure or cancellation. Parsing and password
entry happen outside the short write transaction.

- `imported`: a new dated logical bill, with the first source selected.
- `duplicate`: identical bytes for the same owner/card, even under a different
  filename. Return existing statement/import IDs; do not reparse or add rows.
- `review_candidate`: different bytes plausibly representing an existing bill,
  missing statement dates, or multiple possible matches. Never silently replace
  or combine an existing selected source.

The first selected source is not automatically marked manually reviewed:
`review_status` remains pending. Parser issues are preserved even when source
selection is unambiguous. Duplicate results retain the original review state.

Same-card printed statement dates are conservative matching signals, not proof
that two files are equivalent. Multiple matches create a separate unselected
review record containing possible statement IDs. No date or ownership is
inferred from filenames or neighboring entries.

A card-row lock serializes same-card classification and duplicate rechecks.
Database uniqueness constraints remain the final guard. Lost-response retries
return the existing IDs. The importer does not deduplicate individual merchant
rows; identical-looking purchases remain separate.

Statement totals/reconciliation must use the selected source's entries, not
sum every competing import. There is no candidate promotion/merge or reparse
revision workflow here; that remains FUR-19 and subsequent review work.

## CLI output and exit codes

Output is JSON, preserving the existing CLI contract. Import summaries contain
IDs, status, entry/issue counts, selected-source state, and review status, never
financial descriptions, amounts, PDF contents, or passwords. Lists are paginated
with `limit` (default 50, maximum 200) and `offset`.

- 0: operation completed without known review issues; duplicate no-ops succeed.
- 1: input, configuration, or database operation failed.
- 2: invalid usage, including unknown flags and invalid UUIDs.
- 3: data saved or found, but review is needed.
- 130: cancelled; previously committed files remain saved.

Failure outranks review, and review outranks success regardless of batch order.
Cancellation stops the remaining batch. Driver errors, bound financial values,
and dependency tracebacks are not printed. An interrupted/lost commit response
can be resolved by retrying the same original bytes.

## Retrieve the original

```sh
uv run python -m core original-export --owner OWNER_UUID --import-id IMPORT_UUID
```

The app verifies the stored bytes against the retained original fingerprint
and writes `statement.pdf` to a fresh directory under `data/exports/`.
Directories are 0700 and files 0600. Original filenames are never used as
output paths; arbitrary export destinations are not accepted. The command
prints only the output path, import ID, and SHA-256. Cross-owner lookups fail
without revealing the other owner's import.

If retention previously removed the payload, retrieval reports that it is no
longer retained. An identical-file reimport is still a no-op and does not
silently restore deleted PDF bytes.

## Backup and recovery

`database-backup` requires a compatible native `pg_dump` client on PATH.
Install a client at least as new as the server's major version; use a compatible
`pg_restore` when restoring. Tool absence or failure is an error, not a
successful backup.

The command creates a custom-format archive of the `hisaab` schema and all its
data, including original binary PDFs. It writes `database.dump` and a
`manifest.json` containing archive SHA-256 and the applied Alembic revision
into a fresh owner-only directory under `data/exports/`. Database credentials
are supplied to pg_dump through its environment, never command arguments or
the manifest. Native stderr is not exposed.

This is an **app-schema backup**, not a backup of Supabase Auth, Storage, or
unrelated schemas. The public Alembic ledger is deliberately not in the
archive; its revision is in the manifest. Pause schema deployments while
taking a backup. PostgreSQL provides a consistent snapshot for ordinary
transactional imports.

**The archive is compressed, not encrypted.** It contains extracted financial
data even when PDFs themselves are password-encrypted. File permissions are
not encryption. Protect backups with appropriate disk/file encryption and
maintain an encrypted off-device copy. Do not upload raw archives to Git,
Linear, or chat. No automated/offsite backup or Supabase-plan entitlement is
assumed.

Restore is deliberately not an app CLI operation:
1. Use only a trusted archive; PostgreSQL archives can execute SQL.
2. Verify its checksum against the manifest.
3. Restore into a fresh, separately provisioned database, never overwrite the
   current live project. Use pg_restore with exit-on-error and no-owner.
4. Verify the five tables, constraints, RLS, IDs, amounts, original fingerprints,
   and selected/candidate state.
5. Only for that verified fresh restore, establish the Alembic ledger using the
   manifest's revision, then run Alembic's metadata check against that target.
   Never stamp an existing database merely to silence migration errors.
6. Review privileges and configuration before switching the app to the new DB.

`tests/test_import_recovery.py` demonstrates this procedure end-to-end using
native pg_dump/pg_restore in a disposable PostgreSQL container. It never reads
the application's private connection file or resets the hosted project.

## Retention and limits

Retention settings remain configurable. No automatic deletion or scheduler
is added. With cleanup disabled, old PDFs are still stored; imports do not
silently apply a fixed 24-month cutoff. Extracted data remains indefinitely.
Changes to policy for existing PDFs still need review before cleanup is built.

No allocations, categorization, settlement, email ingestion, OCR, automatic
card discovery, or authenticated multi-user access is introduced. PostgreSQL
is the supported persistence backend; engine portability still requires
backend-specific migrations, security, and tests.

## Verification

The normal test suite uses invented data. Enable disposable PostgreSQL tests
using `HISAAB_TEST_DATABASE_URL` as in the [schema guide](schema/README.md).
Set `HISAAB_TEST_POSTGRES_CONTAINER` to that test container's ID to include the
native recovery drill. CI supplies both. No hosted credentials are needed.

```sh
uv run python -m unittest discover -s tests -v
```

Coverage includes immutable snapshots, encrypted PDF byte round trips, all-bank
entry mapping, renamed no-ops, concurrency, candidates, ambiguous/missing dates,
same-looking purchases, rollback, owner scoping, redaction, batch precedence,
retrieval, and native archive recovery.

Sources: [SQLAlchemy row locking](https://docs.sqlalchemy.org/en/21/core/selectable.html#sqlalchemy.sql.expression.GenerativeSelect.with_for_update),
[pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
and [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
