# Import your first statement

Hisaab imports PDFs through a local Python command. Sign in using the **same
email and password as the hosted UI**. The PDF is parsed on your computer, then
its original bytes and extracted entries are saved through authenticated
Supabase APIs. No Python server runs in the backend.

You do **not** need database credentials, a private configuration file, Node.js,
npm, a local UI server, or manual Python virtual-environment activation.

## One-time setup

Install [Git](https://git-scm.com/downloads) and
[uv](https://docs.astral.sh/uv/getting-started/installation/). You also need
repository access and an existing Hisaab account linked to your data profile.
Use macOS, Linux, or Windows with WSL for these terminal examples.

```sh
git clone https://github.com/furquan1993/hisaab.git
cd hisaab
uv sync --locked
mkdir -p data
```

If you already cloned Hisaab, use that folder. To update an existing clean clone,
run `git pull --ff-only`, then `uv sync --locked`. uv creates `.venv` and can
install the pinned Python version automatically; no activation is needed.
See [uv's project guide](https://docs.astral.sh/uv/guides/projects/).

The project URL and public publishable key are included in
[`supabase.public.json`](../supabase.public.json), shared with the UI. They
identify the project and application; your sign-in authorizes access to your
profile. A publishable key alone cannot import data.

The operator must deploy migration `0020_authenticated_imports` once before this
flow can work on a hosted database. It adds the authenticated import API without
requiring a Python service. If you see `import_api_unavailable`, contact the
workspace operator; do not attempt a migration using your login or public key.

## Each time you import

1. In the hosted UI, open **Cards**. Add the correct physical card if it is not
   saved yet. HDFC, SBI and YES Bank layouts are supported. For another month's
   statement, use the same existing card.
2. Copy the **original PDF** into this clone's `data/` folder. Use your file
   manager; do not use a shortcut/symlink pointing outside that folder.
3. Open **Imports → Import or reparse a statement** in the UI. Choose
   **Card to import into**, copy its command, and replace only the PDF path.
   Run it from the `hisaab` root folder, where `pyproject.toml` is located.
   Quote paths with spaces.
4. Enter your **UI email**, then your **UI password** when prompted. Password
   entry is hidden. If the statement is encrypted, a separate **PDF password**
   prompt follows. Neither password is saved or accepted as a command flag.
5. Return to **Imports** and select **Reload imports**. Inspect the extraction,
   review statement warnings, or review a candidate before relying on totals.
   Reload other statement views if they were already open.

You can also start without copying IDs from the UI:

```sh
uv run python -m core import-pdf "data/October statement.pdf"
```

After sign-in, this lists only your cards and asks you to select one by number.
To preselect a card or skip the email prompt, use:

```sh
uv run python -m core import-pdf --email you@example.com --card CARD_UUID "data/October statement.pdf"
```

Replace `CARD_UUID` with the saved card ID shown in the UI. The password still
uses hidden input. A UI-generated `--owner` is an optional safety check: the
command fails if you sign in to a different profile. It never grants access to
that owner. The server always derives ownership from your authenticated session.

One command may import several PDFs for the same card by listing several paths.
Sign-in happens once per command. Its session stays in memory, refreshes during
long runs, and is closed afterward without signing your browser out. No browser
session tokens, passwords, or database credentials need to be copied.

## Understanding the result

| Result | What to do |
| --- | --- |
| `imported` | The statement was saved; inspect its dates, amounts, card identity, and warnings against the PDF. |
| `duplicate` | This original PDF already exists for your card. No second copy was created; encrypted duplicates do not need the PDF password again. |
| `review_candidate` | Review the new source in Imports. It has not silently replaced an existing published statement. |
| Exit code `3` | Data was saved or found, but review is needed; this is not a generic import failure. |
| Exit code `1` or `2` | Correct the reported sign-in, file, or command problem, then retry. |

Each file is one atomic operation. Earlier successful files remain saved if a
later file fails or you cancel. If a connection drops before success is
confirmed, retry the same original PDF: duplicate detection prevents another
copy. Extraction facts are produced by your local parser; the server validates
ownership, the original fingerprint, structure, amounts, and provenance rather
than independently re-parsing the PDF.

The authenticated path currently accepts original PDFs up to **20 MiB** with up
to **10,000 extracted entries** per file. Original PDF encryption is preserved;
the PDF password is used only by your local parser and is never sent to Supabase.

Keep your clone for next time. Importing another PDF does not require cloning
again, restarting the hosted UI, or redeploying the website.

## Common problems

| Problem | Next step |
| --- | --- |
| `git` or `uv` not found | Install it using the links above, then reopen the terminal. |
| Cloning denied | Authenticate to GitHub and obtain repository access from its owner. |
| Cannot find `core` or the project | Change into the cloned `hisaab` root folder, not `web/`. |
| Sign-in failed | Use your UI email/password, not a database or PDF password. Check project availability and retry. |
| Account/profile not linked | Ask the operator to link your UI account to your existing Hisaab profile. Do not create another owner. |
| Card missing or owner mismatch | Sign in to your own account; add/select the card in the UI and copy a fresh command. |
| `import_api_unavailable` | The operator must deploy the authenticated import migration. |
| PDF path rejected | Copy the real PDF into this clone's `data/` folder and quote paths with spaces. |
| PDF password required/incorrect | Run in your own interactive terminal and use the statement's password. |
| Import rejected | Check the selected card's bank, file size, and parser version. Update the clone and dependencies if needed. |
| Network/session error | Run the command again, sign in, and retry the same PDF. Duplicate retries are safe. |
| Imported data missing in UI | Reload Imports and confirm you used the same project/profile/card. |

## Operators: project overrides, migrations and legacy commands

Ordinary import users need none of the settings in this section.

For a separate test or self-hosted project, create a JSON file containing `url`
and `publishable_key` and explicitly select it with
`import-pdf --project-config PATH`. HTTPS is required except for localhost tests.
Use only a publishable or legacy anon key; secret/service-role keys are rejected.
Never put passwords or sessions in this public JSON. Configure both frontend
`VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` overrides for the same
project. The CLI prints the target project before prompting for credentials.

**Migrations still require private PostgreSQL credentials.** Publishable keys
and user sessions do not grant database DDL access. Keep using the existing
Git-ignored, owner-only `config.local.toml` and the reviewed backup/rehearsal
procedure in [browser workspace](browser-workspace.md#operator-rollout-only-after-review-and-explicit-approval).
Import commands never migrate the database automatically.

For compatibility, explicitly passing `--config` selects the old operator-only
**direct database** import mode. It does not use your UI login and requires both
owner and card IDs:

```sh
uv run python -m core import-pdf --config config.local.toml --owner OWNER_UUID --card CARD_UUID data/statement.pdf
```

Do not add `--config` to ordinary email/password imports. Reparse, backup,
owner-linking and other legacy operator commands still use private database
configuration. See the [statement-loading reference](statement-imports.md) and
[connection reference](../README.md#private-database-connection).

Sources: [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys),
[Supabase Auth](https://supabase.com/docs/guides/auth),
[database function security](https://supabase.com/docs/guides/database/functions).
