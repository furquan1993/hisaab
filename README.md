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

**Privacy:** `data/` is ignored by Git. New run directories are owner-only (0700), and result files are owner-readable/writable (0600). JSON files contain **unencrypted financial data**; file permissions are not encryption. Keep them local and delete experiment results when finished. No decrypted PDF is written, and no document is uploaded. The app's planned 24-month retention policy is not implemented by this probe.

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
