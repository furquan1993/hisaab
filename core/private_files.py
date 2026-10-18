"""Fresh owner-only local files; never accept arbitrary export destinations."""

import json
import os
import tempfile
from pathlib import Path

from core.config import CONFIG_ROOT
from core.persistence.store import StoreError


def export_file(data: bytes, filename: str, *, metadata=None) -> Path:
    """Names are application constants, not filenames supplied by a statement."""
    if filename not in ("statement.pdf", "database.dump"):
        raise StoreError("output_not_allowed", "Unsupported private export type.")
    root = (CONFIG_ROOT / "data" / "exports").resolve()
    if not root.is_relative_to(CONFIG_ROOT):
        raise StoreError(
            "output_not_allowed", "Export directory must be inside the project."
        )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    destination = directory / filename
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        if metadata is not None:
            fd = os.open(
                directory / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as manifest:
                json.dump(metadata, manifest, indent=2)
                manifest.write("\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        (directory / "manifest.json").unlink(missing_ok=True)
        directory.rmdir()
        raise
    return destination
