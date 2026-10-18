import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.imports import _snapshot
from core.persistence.store import StoreError


class ImportPathTests(unittest.TestCase):
    def test_paths_and_symlinks_cannot_escape_the_upload_root(self):
        with (
            tempfile.TemporaryDirectory() as root,
            tempfile.TemporaryDirectory() as outside,
        ):
            path = Path(outside) / "private.pdf"
            path.write_bytes(b"synthetic-sensitive-data")
            with patch("core.imports.INPUT_ROOT", Path(root).resolve()):
                for target in (path, Path(root) / ".." / path.parent.name / path.name):
                    with (
                        self.assertRaises(StoreError),
                        patch("core.imports.os.open") as opened,
                    ):
                        _snapshot(target)
                    opened.assert_not_called()
                if os.name == "posix":
                    link = Path(root) / "link.pdf"
                    link.symlink_to(path)
                    with self.assertRaises(StoreError):
                        _snapshot(link)

    def test_nonregular_files_do_not_block(self):
        if os.name != "posix":
            self.skipTest("POSIX FIFO")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pipe.pdf"
            os.mkfifo(path, 0o600)
            with patch("core.imports.INPUT_ROOT", Path(root).resolve()):
                with self.assertRaises(StoreError):
                    _snapshot(path)
