"""Native pg_dump/pg_restore drill, exclusively within disposable test PostgreSQL."""

import json
import os
import subprocess
import unittest
from hashlib import sha256
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, select, text

from core.backup import backup_database
from core.imports import import_pdf
from core.persistence.models import Base
from tests.import_fixture import ImportTestsBase
from tests.postgres_fixture import migration_config
from tests.test_snapshot import encrypt, statement_bytes

CONTAINER = os.environ.get("HISAAB_TEST_POSTGRES_CONTAINER")


def rows(engine):
    with engine.connect() as connection:
        return {
            table.name: connection.execute(select(table).order_by(table.c.id))
            .mappings()
            .all()
            for table in Base.metadata.tables.values()
        }


@unittest.skipUnless(
    CONTAINER, "Disposable PostgreSQL container required for native recovery drill"
)
class ImportRecoveryTests(ImportTestsBase):
    def test_native_archive_restores_ids_amounts_originals_and_candidates(self):
        self.path.write_bytes(encrypt(self.path.read_bytes()))
        import_pdf(
            self.engine, self.owner, self.card, self.path, password="synthetic-password"
        )
        self.path.write_bytes(statement_bytes("SECOND SYNTHETIC SOURCE"))
        import_pdf(self.engine, self.owner, self.card, self.path)
        before = rows(self.engine)
        native_run = subprocess.run

        def dump_in_container(args, **kwargs):
            # Test-only transport: run the actual pg_dump binary over its local socket.
            return native_run(
                [
                    "docker",
                    "exec",
                    CONTAINER,
                    "pg_dump",
                    "-U",
                    "hisaab_test",
                    "-d",
                    self.engine.url.database,
                    *args[1:],
                ],
                capture_output=True,
                check=False,
                timeout=60,
            )

        with (
            patch("core.backup.shutil.which", return_value="pg_dump"),
            patch("core.backup.subprocess.run", side_effect=dump_in_container),
            patch("core.private_files.CONFIG_ROOT", self.root),
        ):
            archive = backup_database(self.engine)
        manifest = json.loads((archive.parent / "manifest.json").read_text())
        self.assertEqual(sha256(archive.read_bytes()).hexdigest(), manifest["sha256"])
        target = "hisaab_test_restore_" + uuid4().hex
        created = False
        restored = None
        try:
            result = native_run(
                ["docker", "exec", CONTAINER, "createdb", "-U", "hisaab_test", target],
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0)
            created = True
            result = native_run(
                [
                    "docker",
                    "exec",
                    "-i",
                    CONTAINER,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "-U",
                    "hisaab_test",
                    "-d",
                    target,
                ],
                input=archive.read_bytes(),
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0)
            restored = create_engine(
                self.engine.url.set(database=target), hide_parameters=True
            )
            self.assertEqual(rows(restored), before)
            with restored.begin() as connection:
                config = migration_config(connection)
                config.stdout = StringIO()
                # Only a fresh isolated DB restored from this verified manifest is stamped.
                command.stamp(config, manifest["revision"])
                command.check(config)
                flags = (
                    connection.execute(
                        text(
                            "SELECT c.relrowsecurity FROM pg_class c JOIN pg_namespace n "
                            "ON n.oid=c.relnamespace WHERE n.nspname='hisaab' AND c.relkind='r'"
                        )
                    )
                    .scalars()
                    .all()
                )
                self.assertEqual(flags, [True] * len(Base.metadata.tables))
        finally:
            if restored is not None:
                restored.dispose()
            if created:
                result = native_run(
                    [
                        "docker",
                        "exec",
                        CONTAINER,
                        "dropdb",
                        "-U",
                        "hisaab_test",
                        target,
                    ],
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0)
