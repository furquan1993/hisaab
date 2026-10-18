"""Explicit, atomic ORM units of work; no implicit schema creation.

https://docs.sqlalchemy.org/en/21/orm/session_transaction.html
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            yield session
