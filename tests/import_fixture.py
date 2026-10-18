import tempfile
from pathlib import Path
from unittest.mock import patch

from core.persistence.store import register_card, register_owner
from tests.postgres_fixture import PostgresTests
from tests.test_snapshot import statement_bytes
from tests.test_transactions_postgres import remove_synthetic_owner


class ImportTestsBase(PostgresTests):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        scope = patch("core.imports.INPUT_ROOT", self.root)
        scope.start()
        self.addCleanup(scope.stop)
        self.owner = self.other_owner()
        self.card = register_card(
            self.engine, self.owner, bank="hdfc", label="Synthetic card"
        )
        self.path = self.root / "statement.pdf"
        self.path.write_bytes(statement_bytes())

    def other_owner(self):
        owner = register_owner(self.engine, "Synthetic owner")
        self.addCleanup(remove_synthetic_owner, self.engine, owner)
        return owner
