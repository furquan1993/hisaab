This repository hold the code which can be run to fetch all the credit card statements from my emails. After fetching it will parse them, dedupe and update an ongoing database and show it with a nice UI.

## Statement parsers

The core parser supports the supplied HDFC Regalia, HDFC Swiggy, SBI, and YES Bank layouts. Bank detection uses statement content, not filenames. It produces one standard JSON row per entry, including purchases, payments, cashback, fees, taxes, reversals, and unclassified credits. It does not assign spending categories or funding sources.

```sh
uv sync
uv run python -m core parse data/hdfc_regalia_statement.pdf data/hdfc_swiggy_statement.pdf
```

SBI and YES Bank use the same command and output contract:

```sh
uv run python -m core parse data/sbi_card_statement.pdf data/yes_bank_statement.pdf
```

Run this in your own terminal. Encrypted PDFs prompt for a hidden password; the CLI never accepts passwords as command-line arguments or writes them to disk. An unencrypted PDF needs no prompt.

For review without reopening the PDFs, use the previously generated extraction JSON:

```sh
uv run python -m core parse-probe data/probes/run-_wpg2cjh/hdfc_regalia_statement.json data/probes/run-_wpg2cjh/hdfc_swiggy_statement.json
```

Each input creates `data/parsed/run-*/transactions.json`. Open that file in your editor to inspect every row, exact amounts, source locations, raw text, review issues, and per-currency debit/credit totals. The terminal prints only a JSON summary and the output path. Add `--show-transactions` to explicitly print financial records too, or `--output-dir PATH` to choose another output base. Financial output is plaintext; files are 0600 inside new 0700 directories, not encrypted. Keep custom output paths out of Git too.

Exit codes: **0** parsed without known review issues, **1** input/output failure, **2** invalid command arguments, **3** output saved but review is needed, **130** cancelled. When parsing multiple inputs, a failure takes precedence over review-needed status; other inputs are still attempted. Exit 3 is expected for the Regalia sample's two unclassified credits; their amounts/directions are retained, not guessed to be refunds.

Current reference checks account for **27 Regalia entries and 15 Swiggy entries**. Every row's date, time, full description, amount, direction, currency, page, and entry type is checked against local private references. These checks use the existing extraction snapshots; fresh encrypted-PDF-to-output validation on your real originals still requires local password entry. Synthetic AES-256 PDFs exercise the full decryption-to-output path automatically.

SBI and YES Bank were developed tests-first and checked against three encrypted original PDFs each: **14 SBI entries and 35 YES Bank entries**. Independent references were captured before the adapters existed, using source text for SBI and ruled table cells for YES Bank. Missing SBI tax dates remain null; unexplained credits remain unknown. SBI image-only pages were visually inspected locally as promotional material, but unreadable pages still request coverage review rather than being silently assumed blank.

See the [common contract and HDFC guide](docs/hdfc-parser.md) and [SBI/YES Bank validation guide](docs/parser-validation.md). Implementation tracking remains in [Linear](https://linear.app/furquan/project/hisaab-f672b4a38a9f).

## Statement loading

The [statement-loading guide](docs/statement-imports.md) covers owner/card setup,
atomic imports, duplicate no-ops, review candidates, original retrieval, and
private PostgreSQL backup/recovery.

```sh
uv run python -m core owner-create "Primary"
uv run python -m core card-create --owner OWNER_UUID --bank hdfc --label "Regalia"
uv run python -m core import-pdf --owner OWNER_UUID --card CARD_UUID data/statement.pdf
uv run python -m core imports-list --owner OWNER_UUID
```

Use returned UUIDs and the correct physical card. Importing writes to the
configured database; parsing alone does not. Originals are stored unchanged,
including PDF encryption, never reconstructed from extracted pages. No real
statements were loaded during implementation. Review/merge this feature and
establish a backup before the first controlled hosted load.

## Static review workspace

The static React + TypeScript + Vite workspace combines cards in statement-date
and transaction-date views, with independent Account/Category assignments,
reasoned corrections, separate statement coverage review, explicit parser-revision
comparison, and original evidence/downloads. Original extracted facts stay unchanged. Supabase Auth and secured managed APIs provide the
data path; no custom app server or privileged browser credentials.

Start with `cd web`, `npm ci`, then `npm run dev`. Open
http://127.0.0.1:5173/hisaab/ and choose **Explore synthetic demo**.
See [setup, security, deployment and verification](docs/browser-workspace.md).
The approved hosted database rollout is complete through `0011_contributions`,
enabling Account/Category management, assignments, reasoned review, source revisions,
monthly reconciliation and per-card contributions.
The rollout included a verified backup restore and migration rehearsal; original
financial data was preserved. Future Auth/API migrations require separate reviewed
rollout approval. Additional real financial loads remain gated.

The monthly **Reconciliation** workspace now adds combined budget-account summaries
with separate currencies and per-card full/partial contributions. Arrears retain
their original statement month; receipts persist and corrections require explicit
balance review. Summary totals are derived from existing evidence, not copied
monthly charges. Migrations `0010_funding_totals` and `0011_contributions` have been
applied to the hosted database after explicit approval, verified backup/restore,
rehearsal and rollback-only live checks. Public frontend hosting remains a separate
blocked rollout. See [reconciliation and contributions](docs/reconciliation.md).

## Private database connection

The app has private connection configuration plus an approved five-entity
SQLAlchemy model and an initial Alembic migration. See the [ER diagram and
schema/migration guide](docs/schema/README.md). Initial revision
`0001_initial_schema` was deployed on 2026-10-18. Ordinary parsing and db-check
never create tables or import data.

Create `config.local.toml` at the repository root using `config.example.toml`
as the template, without overwriting an existing private configuration. Make the
private file owner-only before entering credentials:

```sh
chmod 600 config.local.toml
```

Copy the separate fields from Supabase's **Connect** dialog into the
`[database]` section: `host`, integer `port`, `database`, `user`, and `pass`.
Quote every string, including `pass`; use the literal password without URL
encoding. The port defaults to 5432. Keep `sslmode = 'require'` unless you have
configured stronger certificate verification. Follow `config.example.toml`.

Alternatively, use `database.url` instead of the separate fields. In URL form,
reserved password characters must be percent-encoded. A blank `url` is ignored
when separate fields are supplied; a nonempty URL mixed with fields is rejected
as ambiguous. Never paste credentials into chat, command arguments, Git, or
logs. The private file is explicitly Git-ignored; the example has no real secrets.

The app reads that same private file using Python's standard `tomllib`.
Its default path is relative to the project, not the current working directory.

```sh
uv sync
uv run python -m core db-check
```

The check executes `SELECT 1`, closes the connection, and prints only a JSON
success or sanitized error. It returns 0 for success, 1 for configuration or
connection failure, 2 for invalid arguments, and 130 for cancellation.
An empty configuration deliberately fails without opening a network connection.
The optional `db-check --config PATH` selects another private TOML file inside
the project directory. Paths escaping that directory (including symlink escapes)
and nonregular files are rejected before reading. Custom files are not
automatically Git-ignored; keep them under `data/` or add an explicit exclusion.

SQLAlchemy **2.1.5** supplies the database boundary, with Psycopg **3.3.6** for
PostgreSQL. Standard `postgresql://` and `postgres://` URIs are normalized to
the Psycopg driver. PostgreSQL connections default to `sslmode=require`;
`verify-ca` and `verify-full` are preserved when explicitly configured.
Requiring TLS encrypts transport but is not the hostname verification of
`verify-full`. Connection attempts default to a 10-second driver timeout per
host/address, not a strict overall deadline.

Supabase's direct host generally needs IPv6 unless an IPv4 option is enabled.
If it is unreachable from your network, copy the **session pooler** URI from the
same Connect dialog instead. Automatic prepared statements are disabled for
compatibility with transaction pooling too.

**Security boundary:** direct credentials authenticate a database role, not a
Hisaab user. A privileged role can bypass row-level security. These credentials remain for the trusted
single-user operator CLI, not for application login or browser distribution. Do not
distribute these credentials to another user. The TOML file contains plaintext
secrets; permissions and Git exclusions are not encryption.

Future SQL backends require the appropriate driver, migrations, and tests;
SQLAlchemy does not make authentication or every schema portable automatically.
No interim SQLite persistence is introduced; an in-memory SQLite test exercises
the generic connection check without a network or file database.

Schema tests use a disposable local PostgreSQL database and never the private
application connection. The [schema guide](docs/schema/README.md) documents
migration/constraint tests and CI. Application connectivity tests do not contact
your hosted database unless explicitly enabled:

```sh
uv run python -m unittest tests.test_config tests.test_database -v
HISAAB_DB_TESTS=1 uv run python -m unittest tests.test_database.LiveConnectionTests -v
```

Sources: [SQLAlchemy engines](https://docs.sqlalchemy.org/en/21/core/engines.html),
[Psycopg dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg),
[Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
and [Python TOML parsing](https://docs.python.org/3/library/tomllib.html).

## Local statement extraction experiment

This experiment evaluates **pdfplumber 0.11.10** against the four sample PDFs. It is not yet a bank-specific parser: extracted table candidates are not validated transaction rows.

### Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```sh
uv sync
uv run python scripts/probe_statements.py
```

The workspace pins Python 3.11.15 in `.python-version`. `uv sync` creates or updates `.venv/` and installs the runtime and development dependencies recorded in `uv.lock`. No manual activation is needed. If the pinned Python is unavailable, uv can download it automatically.

`pyproject.toml` is the dependency source of truth; commit it together with `uv.lock` and `.python-version` when dependencies or the interpreter change. The old requirements files have been replaced. The repository is currently a script-based project, so uv manages dependencies without building or installing Hisaab as a package.

Run the probe yourself in a terminal: it requires interactive password entry and is not yet suitable for an unattended scheduler.

The script processes PDFs directly inside `data/` and prompts for each password with hidden input. Press Enter for an unencrypted PDF. Passwords are used in memory only, not saved or accepted as command-line arguments. Run this yourself in an interactive terminal; piped input is rejected. You can test just one file:

```sh
uv run python scripts/probe_statements.py data/sbi_card_statement.pdf
```

Results go into a fresh `data/probes/run-*/` directory. Each PDF produces JSON containing page text, positioned words, and table candidates using both line-based and text-alignment strategies. The terminal displays only counts and output paths. Incorrect passwords and extraction failures are reported without raw document errors; other PDFs are still attempted. A failed input produces a nonzero exit status. Rerun the command to retry.

**Privacy:** `data/` is ignored by Git. New run directories are owner-only (0700), and result files are owner-readable/writable (0600). JSON files contain **unencrypted financial data**; file permissions are not encryption. Keep them local and delete experiment results when finished. No decrypted PDF is written, and no document is uploaded. Configurable PDF retention and cleanup are not implemented by this probe.

### Automated tests

```sh
uv sync
uv run python -m unittest discover -s tests -v
```

The `dev` dependency group is installed by default and contains the PDF-generation/encryption tools used only by tests. uv project management follows the [official project guide](https://docs.astral.sh/uv/guides/projects/).

Tests use synthetic PDFs, including AES-256 encryption for all supported banks. They cover text/table extraction, wrong passwords, unencrypted/corrupt inputs, private output permissions, continued processing after an error, and rejection of noninteractive password input. Real bank-layout accuracy still requires inspecting the local sample results.

The six SBI/YES Bank original-PDF checks are opt-in and require local private references under `data/expected/banks/` and the Git-ignored, owner-only `credit_card_cred.env` file with `SBI_PASS` and `YESBANK_PASS` assignments:

```sh
HISAAB_PRIVATE_BANK_TESTS=1 uv run python -m unittest tests.test_bank_private -v
```

Only these opt-in tests read that credential file; the normal CLI still prompts privately. Never commit credentials, original statements, extracted references, or real transaction fixtures.

Sources: [pdfplumber loading and password support](https://github.com/jsvine/pdfplumber#loading-a-pdf), [text extraction](https://github.com/jsvine/pdfplumber#extracting-text), and [table extraction strategies](https://github.com/jsvine/pdfplumber#extracting-tables).

## Disabled Skills
Following skills are disable when working with pi in this project
### Development and workflows
 - pr-review
 
 ### Operations
 - argo-cli
 - kibana-logs

 ### Atlassian and company context
 - twg
 - twg-agentic-search
 - twg-artifacts
 - twg-code-review
 - twg-confluence
 - twg-context-discovery
 - twg-engineering-work
 - twg-jira
 - twg-jira-resolve-merged-work
 - twg-operational-health
 - twg-responsibility-routing
 - twg-space-creation
 - twg-status-rollups
