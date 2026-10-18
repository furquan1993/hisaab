"""Shared lazy engine factory and read-only connection probe.

Engine and driver options:
https://docs.sqlalchemy.org/en/21/core/engines.html
https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool

from core.config import ConfigurationError, DatabaseConfig


class DatabaseError(Exception):
    code = "database_unavailable"


def create_database_engine(config: DatabaseConfig) -> Engine:
    """Create a lazy engine shared by connection checks and Alembic."""
    try:
        url = make_url(config.url)
    except (ArgumentError, ValueError):
        raise ConfigurationError(
            "config_invalid",
            "Database URL is invalid; use a SQLAlchemy connection URI.",
        ) from None
    connect_args = {}
    if url.drivername in ("postgres", "postgresql", "postgresql+psycopg"):
        query = dict(url.query)
        query.setdefault("sslmode", "require")
        if query["sslmode"] not in ("require", "verify-ca", "verify-full"):
            raise ConfigurationError(
                "config_invalid", "PostgreSQL connections must require TLS."
            )
        url = url.set(drivername="postgresql+psycopg", query=query)
        connect_args = {
            "connect_timeout": config.connect_timeout_seconds,
            # Compatible with Supabase's transaction pooler as well as direct connections.
            "prepare_threshold": None,
        }
    try:
        return create_engine(
            url,
            connect_args=connect_args,
            poolclass=NullPool,
            echo=False,
            hide_parameters=True,
        )
    except Exception:
        raise DatabaseError(
            "Cannot initialize the configured database driver."
        ) from None


def check_connection(config: DatabaseConfig) -> None:
    """Execute SELECT 1, roll back the implicit transaction, and close resources."""
    engine = create_database_engine(config)
    try:
        try:
            with engine.connect() as connection:
                if connection.execute(text("SELECT 1")).scalar_one() != 1:
                    raise DatabaseError("Unexpected connection-check result.")
        finally:
            engine.dispose()
    except Exception:
        # Driver errors may contain connection details. Never render them publicly.
        raise DatabaseError(
            "Cannot connect. Check credentials, TLS settings, network access, "
            "and the Supabase direct/session-pooler address."
        ) from None
