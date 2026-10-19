"""Local PDF parsing with user-authenticated, atomic Data API persistence."""

import base64
import getpass
import sys
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

from core.imports import _parse, _snapshot
from core.persistence.store import StoreError
from core.user_api import UserAPI, public_config

MAX_PDF_BYTES = 20 * 1024 * 1024


def _prompt(label):
    print(label, end="", file=sys.stderr, flush=True)
    return input().strip()


def _summary(value):
    """Whitelist server output: never print arbitrary API data or financial rows."""
    try:
        if value["status"] not in ("imported", "duplicate", "review_candidate"):
            raise ValueError
        result = {"status": value["status"]}
        for field in ("owner_id", "card_id", "statement_id", "import_id"):
            result[field] = str(UUID(value[field]))
        for field in ("transaction_count", "review_issue_count"):
            if type(value[field]) is not int or value[field] < 0:
                raise ValueError
            result[field] = value[field]
        for field in ("selected_source", "needs_review"):
            if type(value[field]) is not bool:
                raise ValueError
            result[field] = value[field]
        if value["review_status"] not in ("pending", "reviewed", "rejected"):
            raise ValueError
        result["review_status"] = value["review_status"]
        return result
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StoreError("invalid_import_response", "Could not confirm the import response. Retry the same PDF; duplicates are safe.") from None


def _profile(api, expected_owner):
    data = api.request("/profile?select=id,display_name")
    try:
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError
        owner = UUID(data[0]["id"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StoreError("profile_unavailable", "Your UI profile is not linked. Ask the workspace operator to link your account.") from None
    if expected_owner is not None and expected_owner != owner:
        raise StoreError("owner_mismatch", "The command belongs to a different profile. Copy the command from your own signed-in workspace.")
    return owner


def _cards(api):
    cards = []
    for offset in range(0, 100000, 100):
        page = api.request(f"/cards?select=id,label,bank&order=label,id&limit=100&offset={offset}")
        try:
            if not isinstance(page, list):
                raise ValueError
            for card in page:
                UUID(card["id"])
                if not isinstance(card["label"], str) or card["bank"] not in ("hdfc", "sbi", "yes_bank"):
                    raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            raise StoreError("invalid_cards_response", "Could not load your cards. Check project availability and retry.") from None
        cards.extend(page)
        if len(page) < 100:
            return cards
    raise StoreError("card_limit", "Too many cards to list. Contact the workspace operator.")


def _card(cards, selected_id):
    if selected_id is None:
        if not cards:
            raise StoreError("no_cards", "No saved cards. Add your card in the UI's Cards page, then retry.")
        for index, card in enumerate(cards, 1):
            label = "".join(c for c in card["label"] if c.isprintable())
            print(f"{index}. {label} ({card['bank']})", file=sys.stderr)
        choice = _prompt("Card number from the list: ")
        if not choice.isascii() or not choice.isdecimal() or not 1 <= int(choice) <= len(cards):
            raise StoreError("invalid_card_selection", "Choose a card number from the list and run the command again.")
        return cards[int(choice) - 1]
    selected = next((card for card in cards if card["id"] == str(selected_id)), None)
    if selected is None:
        raise StoreError("card_not_found", "The card is unavailable for your signed-in account. Check Cards in the UI.")
    return selected


def import_one(api, owner, card, path, password_provider):
    data = _snapshot(path)
    if len(data) > MAX_PDF_BYTES:
        raise StoreError("pdf_too_large", "PDF must be at most 20 MiB.")
    digest = sha256(data).hexdigest()
    target = {"p_card": card["id"], "p_sha256": digest}
    existing = api.request("/rpc/find_pdf_import", target)
    if existing is not None:
        result = _summary(existing)
    else:
        parsed = _parse(data, Path(path).name, "", password_provider)
        if parsed.source_sha256 != digest or parsed.input_kind != "pdf":
            raise StoreError("snapshot_mismatch", "Parser evidence does not match the original PDF snapshot.")
        if parsed.bank != card["bank"]:
            raise StoreError("bank_mismatch", "Statement bank does not match the selected card.")
        statement = parsed.to_dict()
        statement["extractor_version"] = "hisaab-extraction-1/pdfplumber-" + version("pdfplumber")
        result = _summary(api.request("/rpc/import_statement", {
            "p_card": card["id"], "p_statement": statement,
            "p_pdf_base64": base64.b64encode(data).decode("ascii"),
        }))
    if result["owner_id"] != str(owner) or result["card_id"] != card["id"]:
        raise StoreError("invalid_import_response", "Could not confirm the import's owner/card. Check the workspace before retrying.")
    return result


def run(args, emit, guard, password_provider):
    if not sys.stdin.isatty():
        raise StoreError("interactive_login_required", "Run import-pdf in your own terminal for UI email/password sign-in. Password flags and piped credentials are not supported.")
    url, key = public_config(args.project_config)
    print("Sign in to " + url + " using your Hisaab UI account.", file=sys.stderr)
    email = args.email or _prompt("UI email: ")
    if not email:
        raise StoreError("email_required", "Enter the email you use to sign in to Hisaab.")
    api = UserAPI(url, key)
    try:
        password = getpass.getpass("UI password (hidden): ")
        try:
            api.sign_in(email, password)
        finally:
            password = None
        owner = _profile(api, args.owner)
        card = _card(_cards(api), args.card)
        code = 0
        for path in args.paths:
            def load():
                saved = import_one(api, owner, card, path, password_provider)
                emit(saved)
                return 3 if saved["needs_review"] else 0
            current = guard(load, emit)
            if current == 130:
                return current
            if current == 1 or code == 0:
                code = current
        return code
    finally:
        api.close()
