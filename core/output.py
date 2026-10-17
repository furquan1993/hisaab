"""Explicit private export of parsed financial records."""

import json
import os
import tempfile
from pathlib import Path

from core.models import Statement


def save_statement(statement: Statement, root: Path) -> Path:
    """Create a fresh owner-only directory/file; never overwrite prior results.

    These are plaintext local records. Permissions do not provide encryption.
    """
    payload = json.dumps(statement.to_dict(), indent=2, ensure_ascii=False) + "\n"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=root))
    destination = directory / "transactions.json"
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(payload)
    except BaseException:
        destination.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return destination
