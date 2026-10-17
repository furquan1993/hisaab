This repository hold the code which can be run to fetch all the credit card statements from my emails. After fetching it will parse them, dedupe and update an ongoing database and show it with a nice UI.

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

Tests use synthetic PDFs, including AES-256 encryption. They cover text/table extraction, wrong passwords, unencrypted/corrupt inputs, private output permissions, continued processing after an error, and rejection of noninteractive password input. Real bank-layout accuracy still requires inspecting the local sample results.

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
