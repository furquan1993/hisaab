"""Explicit PostgreSQL app-schema backup; no credentials in process arguments.

https://www.postgresql.org/docs/17/app-pgdump.html
"""

import os
import shutil
import subprocess
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import text

from core.persistence.store import StoreError
from core.private_files import export_file


def backup_database(engine):
    executable = shutil.which("pg_dump")
    if executable is None:
        raise StoreError(
            "backup_tool_missing",
            "Install a PostgreSQL client containing pg_dump before backing up.",
        )
    url = engine.url
    if url.get_backend_name() != "postgresql" or not all(
        (url.host, url.username, url.database)
    ):
        raise StoreError(
            "backup_unavailable",
            "Backup requires a fully specified PostgreSQL connection.",
        )
    with engine.connect() as connection:
        revisions = (
            connection.execute(
                text("SELECT version_num FROM public.hisaab_schema_version")
            )
            .scalars()
            .all()
        )
    if len(revisions) != 1:
        raise StoreError(
            "backup_unavailable", "A single applied migration revision is required."
        )
    environment = os.environ.copy()
    environment.pop("PGSERVICE", None)
    environment.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGUSER=url.username,
        PGDATABASE=url.database,
        PGSSLMODE=url.query.get("sslmode", "require"),
        PGCONNECT_TIMEOUT="10",
    )
    if url.password is not None:
        environment["PGPASSWORD"] = url.password
    if "sslrootcert" in url.query:
        environment["PGSSLROOTCERT"] = url.query["sslrootcert"]
    try:
        completed = subprocess.run(
            [
                executable,
                "--format=custom",
                "--schema=hisaab",
                "--no-owner",
                "--no-acl",
            ],
            env=environment,
            capture_output=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        raise StoreError(
            "backup_failed", "Backup could not finish; no successful backup reported."
        ) from None
    if completed.returncode != 0 or not completed.stdout.startswith(b"PGDMP"):
        raise StoreError(
            "backup_failed",
            "Backup failed. Check client/server compatibility and backup privileges.",
        )
    metadata = {
        "revision": revisions[0],
        "sha256": sha256(completed.stdout).hexdigest(),
        "scope": "hisaab",
        "format": "pg_dump-custom",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return export_file(completed.stdout, "database.dump", metadata=metadata)
