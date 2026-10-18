from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from unittest.mock import patch

from sqlalchemy import func, select

from core.imports import import_pdf
from core.parser import parse_pdf_bytes
from core.persistence.models import Entry, Statement
from core.persistence.session import transaction
from tests.import_fixture import ImportTestsBase
from tests.test_snapshot import statement_bytes


class ConcurrentImportTests(ImportTestsBase):
    def race(self, first, second):
        barrier = Barrier(2)

        def parse(data, **kwargs):
            parsed = parse_pdf_bytes(data, **kwargs)
            barrier.wait(timeout=10)
            return parsed

        with patch("core.imports.parse_pdf_bytes", side_effect=parse):
            with ThreadPoolExecutor(2) as pool:
                futures = [
                    pool.submit(import_pdf, self.engine, self.owner, self.card, path)
                    for path in (first, second)
                ]
                return [future.result(timeout=20) for future in futures]

    def test_simultaneous_identical_imports_return_one_identity(self):
        one, two = self.race(self.path, self.path)
        self.assertEqual({one.status, two.status}, {"imported", "duplicate"})
        self.assertEqual(one.import_id, two.import_id)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(Entry)), 2
            )

    def test_simultaneous_competing_files_select_only_one_source(self):
        other = self.root / "another.pdf"
        other.write_bytes(statement_bytes("SECOND SYNTHETIC SHOP"))
        results = self.race(self.path, other)
        self.assertEqual(
            {result.status for result in results}, {"imported", "review_candidate"}
        )
        self.assertEqual(len({result.statement_id for result in results}), 1)
        self.assertEqual(sum(result.selected_source for result in results), 1)

    def test_multiple_possible_statements_are_not_guessed(self):
        import_pdf(self.engine, self.owner, self.card, self.path)
        parsed = parse_pdf_bytes(self.path.read_bytes(), source_name=self.path.name)
        with transaction(self.engine) as session:
            session.add(
                Statement(
                    owner_id=self.owner,
                    card_id=self.card,
                    statement_date=parsed.statement_date,
                )
            )
        self.path.write_bytes(statement_bytes("OTHER SYNTHETIC SHOP"))
        result = import_pdf(self.engine, self.owner, self.card, self.path)
        self.assertFalse(result.selected_source)
        self.assertEqual(result.status, "review_candidate")

    def test_different_statement_date_creates_another_selected_bill(self):
        from datetime import date

        first = import_pdf(self.engine, self.owner, self.card, self.path)
        self.path.write_bytes(statement_bytes("SECOND MONTH"))
        parsed = replace(
            parse_pdf_bytes(self.path.read_bytes(), source_name=self.path.name),
            statement_date=date(2030, 1, 31),
        )
        with patch("core.imports.parse_pdf_bytes", return_value=parsed):
            second = import_pdf(self.engine, self.owner, self.card, self.path)
        self.assertTrue(second.selected_source)
        self.assertNotEqual(first.statement_id, second.statement_id)
