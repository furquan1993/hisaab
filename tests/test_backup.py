import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.engine import make_url

from core.backup import backup_database
from core.persistence.store import StoreError


class BackupTests(unittest.TestCase):
    def engine(self):
        engine = MagicMock()
        engine.url = make_url(
            "postgresql+psycopg://user:synthetic-secret@localhost/example?sslmode=require"
        )
        engine.connect.return_value.__enter__.return_value.execute.return_value.scalars.return_value.all.return_value = [
            "0001_initial_schema"
        ]
        return engine

    def test_password_is_environment_only_and_export_is_private(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch("core.private_files.CONFIG_ROOT", Path(root).resolve()),
        ):
            with (
                patch("core.backup.shutil.which", return_value="/example/pg_dump"),
                patch(
                    "core.backup.subprocess.run",
                    return_value=SimpleNamespace(
                        returncode=0, stdout=b"PGDMPsynthetic", stderr=b""
                    ),
                ) as run,
            ):
                destination = backup_database(self.engine())
            self.assertEqual(destination.read_bytes(), b"PGDMPsynthetic")
            self.assertNotIn("synthetic-secret", " ".join(run.call_args.args[0]))
            self.assertEqual(
                run.call_args.kwargs["env"]["PGPASSWORD"], "synthetic-secret"
            )
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertTrue((destination.parent / "manifest.json").exists())

    def test_missing_tool_is_actionable(self):
        with patch("core.backup.shutil.which", return_value=None):
            with self.assertRaises(StoreError) as error:
                backup_database(self.engine())
        self.assertEqual(error.exception.code, "backup_tool_missing")

    def test_dump_failure_does_not_echo_driver_stderr(self):
        with (
            patch("core.backup.shutil.which", return_value="pg_dump"),
            patch(
                "core.backup.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=1, stdout=b"", stderr=b"synthetic-secret"
                ),
            ),
        ):
            with self.assertRaises(StoreError) as error:
                backup_database(self.engine())
        self.assertNotIn("synthetic-secret", str(error.exception))
