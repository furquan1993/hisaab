"""Delete synthetic sidecars in dependency order before their evidence parents."""

from sqlalchemy import inspect
from sqlalchemy.sql.ddl import sort_tables

from core.persistence.models import Base


def remove_decisions(connection, owners):
    evidence = {"owners", "cards", "statements", "imports", "entries"}
    tables = [
        table for table in Base.metadata.tables.values() if table.name not in evidence
    ]
    for table in reversed(sort_tables(tables)):
        if inspect(connection).has_table(table.name, schema=table.schema):
            connection.execute(table.delete().where(table.c.owner_id.in_(owners)))
