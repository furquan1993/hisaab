"""Store CLI boundary: safe JSON only, no raw SQL/driver exceptions."""

import getpass
import sys
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from core.backup import backup_database
from core.config import DEFAULT_CONFIG, ConfigurationError, load_config
from core.user_api import PUBLIC_CONFIG
from core.database import DatabaseError, create_database_engine
from core.extraction import ParseError
from core.imports import import_pdf
from core.persistence.import_records import list_imports, read_original
from core.persistence.store import (
    StoreError,
    link_owner_auth,
    list_cards,
    list_owners,
    register_card,
    register_owner,
    unlink_owner_auth,
)
from core.private_files import export_file
from core.revisions import reparse_import


def add_arguments(subparsers):
    def command(name, help_text):
        parser = subparsers.add_parser(name, help=help_text, allow_abbrev=False)
        parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        return parser

    owner = command(
        "owner-create", "Register a data owner, not an authenticated login."
    )
    owner.add_argument("name")
    linked = command(
        "owner-auth-link", "Privately link an existing owner to a verified Auth user."
    )
    linked.add_argument("owner", type=UUID)
    linked.add_argument("auth_user", type=UUID)
    unlinked = command("owner-auth-unlink", "Revoke the owner's browser data access.")
    unlinked.add_argument("owner", type=UUID)
    owners = command("owners-list", "List registered data owners.")
    card = command("card-create", "Register a card for an explicit owner.")
    card.add_argument("--owner", type=UUID, required=True)
    card.add_argument("--bank", choices=("hdfc", "sbi", "yes_bank"), required=True)
    card.add_argument("--label", required=True)
    card.add_argument("--last-four")
    cards = command("cards-list", "List the selected owner's cards.")
    cards.add_argument("--owner", type=UUID, required=True)
    imported = subparsers.add_parser(
        "import-pdf", help="Sign in with your UI email/password and import local PDFs.",
        allow_abbrev=False,
    )
    imported.add_argument("--project-config", type=Path, default=PUBLIC_CONFIG,
                          help="Public Supabase URL/key JSON (default: supabase.public.json).")
    imported.add_argument("--email", help="UI email; prompts if omitted. Password is always hidden input.")
    imported.add_argument("--config", type=Path,
                          help="Operator-only direct database mode using private TOML; requires --owner and --card.")
    imported.add_argument("--owner", type=UUID, help="Optional expected UI profile ID; never an authentication credential.")
    imported.add_argument("--card", type=UUID, help="Saved card ID; prompts with your cards if omitted.")
    imported.add_argument("paths", nargs="+", type=Path)
    reparsed = command(
        "reparse-import",
        "Propose a parser revision from retained original bytes; never publish automatically.",
    )
    reparsed.add_argument("--owner", type=UUID, required=True)
    reparsed.add_argument("--import-id", type=UUID, required=True)
    imports = command(
        "imports-list", "List import IDs, counts and review/selection state."
    )
    imports.add_argument("--owner", type=UUID, required=True)
    imports.add_argument("--card", type=UUID)
    command(
        "database-backup", "Create a private app-schema archive and migration manifest."
    )
    training = command(
        "assignment-train",
        "Preview historical examples; --apply saves learning and assigns selected entries.",
    )
    training.add_argument("--owner", type=UUID, required=True)
    training.add_argument("--apply", action="store_true")
    training.add_argument("paths", nargs="+", type=Path)
    original = command(
        "original-export", "Export unchanged original PDF bytes privately."
    )
    original.add_argument("--owner", type=UUID, required=True)
    original.add_argument("--import-id", type=UUID, required=True)
    for parser in (owners, cards, imports):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--offset", type=int, default=0)


def _guard(action, emit):
    try:
        return action()
    except (ConfigurationError, DatabaseError, StoreError, ParseError) as error:
        emit({"error": {"code": error.code, "message": str(error)}})
        return 1
    except (KeyboardInterrupt, EOFError):
        emit(
            {
                "error": {
                    "code": "cancelled",
                    "message": "Cancelled; prior committed imports remain saved.",
                }
            }
        )
        return 130
    except Exception:
        emit(
            {
                "error": {
                    "code": "store_operation_failed",
                    "message": "Operation failed; private database and document details suppressed.",
                }
            }
        )
        return 1


def _password():
    if not sys.stdin.isatty():
        raise StoreError(
            "password_required", "Use your own terminal for hidden PDF password entry."
        )
    return getpass.getpass("PDF password (hidden): ")


def _owner(engine, args, emit):
    owner = register_owner(engine, args.name)
    emit({"status": "owner_created", "owner_id": str(owner)})
    return 0


def _auth_link(engine, args, emit):
    if args.command == "owner-auth-link":
        link_owner_auth(engine, args.owner, args.auth_user)
        status = "auth_linked"
    else:
        unlink_owner_auth(engine, args.owner)
        status = "auth_unlinked"
    emit({"status": status, "owner_id": str(args.owner)})
    return 0


def _card(engine, args, emit):
    card = register_card(
        engine, args.owner, bank=args.bank, label=args.label, last_four=args.last_four
    )
    emit({"status": "card_created", "owner_id": str(args.owner), "card_id": str(card)})
    return 0


def _list(engine, args, emit):
    options = dict(limit=args.limit, offset=args.offset)
    if args.command == "owners-list":
        rows = list_owners(engine, **options)
    elif args.command == "cards-list":
        rows = list_cards(engine, args.owner, **options)
    else:
        rows = list_imports(engine, args.owner, card_id=args.card, **options)
    emit(
        {"items": rows, "count": len(rows), "limit": args.limit, "offset": args.offset}
    )
    return 0


def _one_import(engine, args, path, emit):
    saved = import_pdf(engine, args.owner, args.card, path, password_provider=_password)
    emit(saved.to_dict())
    return 3 if saved.needs_review else 0


def _imports(engine, args, emit):
    code = 0
    for path in args.paths:
        current = _guard(lambda: _one_import(engine, args, path, emit), emit)
        if current == 130:
            return current
        if current == 1 or code == 0:
            code = current
    return code


def _reparse(engine, args, emit):
    saved = reparse_import(
        engine, args.owner, args.import_id, password_provider=_password
    )
    emit(
        {
            "status": "review_candidate",
            "revision_id": saved["id"],
            "base_import_id": saved["base_import_id"],
            "candidate_import_id": saved["candidate_import_id"],
            "matched_count": len(saved["plan"]["matches"]),
            "conflict_count": len(saved["plan"]["unmatched_new"]),
        }
    )
    return 3


def _original(engine, args, emit):
    data = read_original(engine, args.owner, args.import_id)
    destination = export_file(data, "statement.pdf")
    emit(
        {
            "status": "exported",
            "import_id": str(args.import_id),
            "output": str(destination),
            "sha256": sha256(data).hexdigest(),
        }
    )
    return 0


def _backup(engine, args, emit):
    destination = backup_database(engine)
    emit(
        {
            "status": "backed_up",
            "output": str(destination),
            "manifest": str(destination.parent / "manifest.json"),
        }
    )
    return 0


def _train(engine, args, emit):
    from core.assignments import load_examples, history_summary, train_assignments

    examples = load_examples(args.paths)
    summary = (
        train_assignments(engine, args.owner, examples)
        if args.apply else history_summary(examples)
    )
    emit({"status": "trained" if args.apply else "preview", **summary})
    return 0


HANDLERS = {
    "assignment-train": _train,
    "owner-create": _owner,
    "owner-auth-link": _auth_link,
    "owner-auth-unlink": _auth_link,
    "owners-list": _list,
    "card-create": _card,
    "cards-list": _list,
    "import-pdf": _imports,
    "reparse-import": _reparse,
    "imports-list": _list,
    "original-export": _original,
    "database-backup": _backup,
}


def run(args, emit):
    def action():
        if args.command == "import-pdf":
            if args.config is None:
                from core import user_imports
                return user_imports.run(args, emit, _guard, _password)
            if args.owner is None or args.card is None or args.email is not None:
                raise StoreError("operator_arguments", "Direct database mode requires --config, --owner and --card, without --email. Omit --config to use your UI login.")
        if args.command == "assignment-train" and not args.apply:
            return _train(None, args, emit)
        engine = create_database_engine(load_config(args.config))
        try:
            return HANDLERS[args.command](engine, args, emit)
        finally:
            engine.dispose()

    return _guard(action, emit)
