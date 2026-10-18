"""Trusted single-user persistence operations with explicit owner scoping.

These checks are not authentication for holders of privileged DB credentials.
"""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from core.persistence.models import Card, Owner
from core.persistence.session import transaction


class StoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@contextmanager
def store_session(engine):
    try:
        with transaction(engine) as session:
            yield session
    except SQLAlchemyError:
        raise StoreError(
            "database_operation_failed",
            "Database operation failed; the transaction was not partially saved.",
        ) from None


def _label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise StoreError(
            "invalid_fields", "Names and labels must contain 1 to 200 characters."
        )
    return value.strip()


def page(limit, offset):
    if (
        type(limit) is not int
        or not 1 <= limit <= 200
        or type(offset) is not int
        or offset < 0
    ):
        raise StoreError(
            "invalid_pagination", "Use a limit from 1 to 200 and a nonnegative offset."
        )


def require_owner(session, owner_id):
    if session.get(Owner, owner_id) is None:
        raise StoreError("owner_not_found", "Selected owner does not exist.")


def require_card(session, owner_id, card_id, *, lock=False):
    query = select(Card).where(Card.owner_id == owner_id, Card.id == card_id)
    if lock:
        query = query.with_for_update()
    card = session.scalar(query)
    if card is None:
        raise StoreError(
            "card_not_found", "Card is not available for the selected owner."
        )
    return card


def link_owner_auth(engine, owner_id: UUID, auth_user_id: UUID):
    """Operator-only binding; browser code has no owner-claim operation."""
    with store_session(engine) as session:
        owner = session.scalar(
            select(Owner).where(Owner.id == owner_id).with_for_update()
        )
        if owner is None:
            raise StoreError("owner_not_found", "Selected owner does not exist.")
        if owner.auth_user_id is not None and owner.auth_user_id != auth_user_id:
            raise StoreError(
                "auth_link_exists",
                "Unlink the current Auth identity explicitly before replacing it.",
            )
        exists = session.scalar(
            text("SELECT EXISTS (SELECT 1 FROM auth.users WHERE id=:subject)"),
            {"subject": auth_user_id},
        )
        if not exists:
            raise StoreError(
                "auth_user_not_found",
                "Create and confirm the Auth user in this project first.",
            )
        occupied = session.scalar(
            select(Owner.id).where(
                Owner.auth_user_id == auth_user_id, Owner.id != owner_id
            )
        )
        if occupied is not None:
            raise StoreError(
                "auth_link_exists", "This Auth identity is already linked to an owner."
            )
        owner.auth_user_id = auth_user_id


def unlink_owner_auth(engine, owner_id: UUID):
    """Immediately revoke application data access, including unexpired JWTs."""
    with store_session(engine) as session:
        owner = session.scalar(
            select(Owner).where(Owner.id == owner_id).with_for_update()
        )
        if owner is None:
            raise StoreError("owner_not_found", "Selected owner does not exist.")
        owner.auth_user_id = None


def register_owner(engine, display_name: str) -> UUID:
    name = _label(display_name)
    with store_session(engine) as session:
        owner = Owner(display_name=name)
        session.add(owner)
        session.flush()
        return owner.id


def register_card(
    engine, owner_id: UUID, *, bank: str, label: str, last_four=None
) -> UUID:
    name = _label(label)
    if bank not in ("hdfc", "sbi", "yes_bank"):
        raise StoreError("invalid_fields", "Select a supported bank.")
    if last_four is not None and (
        not isinstance(last_four, str)
        or len(last_four) != 4
        or not last_four.isascii()
        or not last_four.isdigit()
    ):
        raise StoreError(
            "invalid_fields", "Last four digits must contain exactly four ASCII digits."
        )
    with store_session(engine) as session:
        require_owner(session, owner_id)
        card = Card(owner_id=owner_id, bank=bank, label=name, last_four=last_four)
        session.add(card)
        session.flush()
        return card.id


def list_owners(engine, *, limit=50, offset=0):
    page(limit, offset)
    with store_session(engine) as session:
        rows = session.scalars(
            select(Owner)
            .order_by(Owner.created_at, Owner.id)
            .limit(limit)
            .offset(offset)
        )
        return [{"id": str(row.id), "display_name": row.display_name} for row in rows]


def list_cards(engine, owner_id: UUID, *, limit=50, offset=0):
    page(limit, offset)
    with store_session(engine) as session:
        require_owner(session, owner_id)
        rows = session.scalars(
            select(Card)
            .where(Card.owner_id == owner_id)
            .order_by(Card.created_at, Card.id)
            .limit(limit)
            .offset(offset)
        )
        return [
            {
                "id": str(row.id),
                "bank": row.bank,
                "label": row.label,
                "last_four": row.last_four,
            }
            for row in rows
        ]
