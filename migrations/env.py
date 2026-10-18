"""Alembic is the only schema-change mechanism; never create tables on startup.

Connection sharing / custom configuration:
https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection
"""

from alembic import context
from alembic.util import CommandError

from core.config import load_config
from core.database import create_database_engine
from core.persistence.models import Base

config = context.config


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == "hisaab"
    return True


def configure(connection=None):
    options = dict(
        target_metadata=Base.metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        version_table="hisaab_schema_version",
        version_table_schema="public",
    )
    if connection is None:
        context.configure(dialect_name="postgresql", literal_binds=True, **options)
    else:
        if connection.dialect.name != "postgresql":
            raise CommandError("Migrations currently support PostgreSQL only.")
        context.configure(connection=connection, **options)
    with context.begin_transaction():
        context.run_migrations()


def online():
    supplied = config.attributes.get("connection")
    if supplied is not None:
        configure(supplied)
        return
    settings_path = config.attributes.get("settings_path")
    settings = load_config() if settings_path is None else load_config(settings_path)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            configure(connection)
    finally:
        engine.dispose()


try:
    if context.is_offline_mode():
        configure()
    else:
        online()
except Exception:
    # SQL/driver exception strings can contain URLs or bound values.
    raise CommandError(
        "Migration failed. Check private configuration and database state; "
        "no connection details are printed."
    ) from None
