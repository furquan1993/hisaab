# Import your first statement

Use this guide when you already sign in to the hosted Hisaab workspace and want
to add a PDF statement. PDF upload is not available in the browser yet. You run
the importer on your computer; it saves the original PDF and extracted entries
to the same database that the hosted UI reads.

You do **not** need Node.js, npm, a local UI server, frontend environment
variables, or manual Python virtual-environment activation.

## Before you start

You need access to this repository, [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/), your PDF, and
authorized database access to the same project as your hosted workspace.
The terminal examples below use macOS, Linux, or Windows with WSL.

**This is currently a trusted operator workflow.** A UI login alone does not
grant permission to run imports. The importer connects directly to PostgreSQL,
and privileged database credentials can access more than your signed-in profile.
Do not share the project's database password with ordinary UI users. If you only
have a UI account, ask the workspace operator to handle the import through an
approved private process. There is no self-service CLI login using your UI
email/password yet.

The operator must have completed database setup, linked your existing profile
to your UI account, and established a verified backup before the first real
load. See the [operator reference](statement-imports.md#setup-and-first-controlled-load)
for that separate setup. An existing UI user should not create another owner or
run database migrations just to import a new statement.

## One-time setup on your computer

### 1. Download the repository and install the Python dependencies

Open your terminal in a folder where you keep projects, then run:

```sh
git clone https://github.com/furquan1993/hisaab.git
cd hisaab
uv sync --locked
```

If you already cloned Hisaab, open that folder instead of cloning again. GitHub
may require you to authenticate if the repository is private. If cloning is
denied, obtain repository access from its owner.

uv creates `.venv` and installs the project's dependencies. It can download the
pinned Python version if needed; you do not need to activate `.venv` yourself.
See [uv's project guide](https://docs.astral.sh/uv/guides/projects/).

### 2. Configure the database connection privately

Run these commands from the `hisaab` folder. `cp -n` keeps an existing config;
if you already configured this computer, reuse that file.

```sh
umask 077
cp -n config.example.toml config.local.toml
chmod 600 config.local.toml
```

Open `config.local.toml` in a local text editor. Under `[database]`, replace the
example values using the intended Supabase project's **Connect** dialog:

```toml
[database]
host = 'HOST_FROM_SUPABASE'
port = 5432
database = 'postgres'
user = 'USER_FROM_SUPABASE'
pass = 'YOUR_DATABASE_PASSWORD'
sslmode = 'require'
connect_timeout_seconds = 10
```

Copy the actual port and username shown for your chosen connection. `pass` is
the **database password**, not your Hisaab login password, PDF password, or a
Supabase API key. Keep strings quoted and the port unquoted. Separate fields
use the literal password without URL encoding; TOML special characters must
still be represented correctly. Keep any existing `[retention]` section.

The importer reads this file automatically. Your browser session is not reused,
and `--owner`/`--card` identify records rather than authenticate you. You do not
pass credentials in the import command. The file is Git-ignored but contains
plaintext secrets: keep it private and never paste it into chat or commit it.

Test the connection without importing anything:

```sh
uv run python -m core db-check
```

Continue only after the check succeeds and the operator confirms this is the
database used by your hosted workspace. `db-check` verifies connectivity, not
that you selected the correct project. If the direct host is unreachable on
your network, use the session pooler's fields from **Connect**. See the
[connection reference](../README.md#private-database-connection) for URL-based
configuration and troubleshooting details.

**Optional alternate config:** `--config` selects a TOML file; it is not a
password parameter. Put it after the subcommand, and use the same file for the
connection check and import:

```sh
uv run python -m core db-check --config data/import-config.toml
uv run python -m core import-pdf --config data/import-config.toml --owner OWNER_UUID --card CARD_UUID data/statement.pdf
```

An alternate file must be inside this repository and owner-only (0600). Keeping
it under Git-ignored `data/` avoids accidentally committing it. Replace the UUID
placeholders using the UI as described below. With the default
`config.local.toml`, omit `--config` entirely.

## Each time you import a statement

1. In the hosted UI, open **Cards**. Add the correct physical card if it is not
   already saved. Choose its bank carefully: HDFC, SBI, and YES Bank layouts are
   supported. Use the existing card when importing another month for that card.
2. In your local `hisaab` folder, create `data/` if needed:
   `mkdir -p data`. Copy your original PDF into that folder using your file
   manager. Do not use a shortcut or symlink to a file outside `data/`.
3. In the UI, open **Imports → Import or reparse a statement** and select
   **Card to import into**. Copy the generated command; it already contains
   your owner and selected card IDs. Replace only `data/statement.pdf` with
   the path to your copied file. Quote paths containing spaces.
4. Run the command in a terminal from the repository root (the folder containing
   `pyproject.toml`, not `web/`). For example, the command has this shape:

   ```sh
   uv run python -m core import-pdf --owner OWNER_UUID --card CARD_UUID "data/October statement.pdf"
   ```

   Use the actual IDs from the UI, not the placeholder words above. An encrypted
   PDF prompts for its password in the terminal. Nothing appears while you type;
   press Enter when finished. The PDF password is used in memory and is not saved.
5. Read the result, then return to **Imports** and choose **Reload imports**.
   Use **Inspect extraction**, **Review statement**, or **Review candidate** as
   appropriate. Check dates, amounts, card identity, and any warnings against
   your PDF before relying on the totals. Reload the relevant statement view if
   you had it open already.

| Result | What to do |
| --- | --- |
| `imported` | The statement was saved; inspect it and review any warnings. |
| `duplicate` | The same PDF already exists for this card; no second copy was imported. |
| `review_candidate` | The source needs review; it has not silently replaced an existing statement. |
| Exit code `3` | Data was saved or found, but review is needed. This is not a generic import failure. |
| Exit code `1` or `2` | Read the error, correct the connection/file/arguments, then retry. |

Keep the clone and private config for later imports. You do not need to clone
again, restart the hosted UI, or redeploy the site when you import another PDF.
If you update the clone with `git pull --ff-only`, run `uv sync --locked` again.
Do not run migration commands as part of routine imports.

## Common problems

| Problem | Next step |
| --- | --- |
| `git` or `uv` is not found | Install it using the links above, then reopen the terminal. |
| Python cannot find `core`, or uv cannot find the project | Change into the cloned `hisaab` root folder. |
| Missing, incomplete, or invalid config | Edit the private `config.local.toml`; replace the example fields and check TOML syntax. |
| Config permissions rejected | Run `chmod 600 config.local.toml` on the file you are using. |
| Connection fails | Check the project, host, port, database username/password, and network access; try the session pooler if needed. |
| PDF path rejected | Copy the real PDF inside this clone's `data/` folder and quote paths with spaces. |
| PDF password required or incorrect | Run interactively in your own terminal and use the statement's password, not the database password. |
| Saved cards or imported data are missing | Confirm the UI and local config use the same project and the selected owner/card IDs are correct; reload Imports. |

For backups, original-PDF export, batch behavior, and detailed import rules,
see the [statement-loading reference](statement-imports.md).
