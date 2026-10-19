"""Model contract tests; no hosted database access."""

import unittest

from sqlalchemy import LargeBinary, Numeric, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from core.persistence.models import (
    Base,
    Card,
    Contribution,
    Entry,
    ImportRecord,
    Owner,
    Statement,
)


class ModelContractTests(unittest.TestCase):
    def test_five_immutable_evidence_entities_and_review_sidecars(self):
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "hisaab.owners",
                "hisaab.cards",
                "hisaab.statements",
                "hisaab.imports",
                "hisaab.entries",
                "hisaab.categories",
                "hisaab.accounts",
                "hisaab.entry_decisions",
                "hisaab.entry_descriptions",
                "hisaab.decision_events",
                "hisaab.parser_revisions",
                "hisaab.entry_links",
                "hisaab.import_reviews",
                "hisaab.contributions",
                "hisaab.funding_confirmations",
                "hisaab.assignment_examples",
                "hisaab.spending_groups",
                "hisaab.spending_assignments",
                "hisaab.spending_events",
            },
        )
        configure_mappers()

    def test_pdf_is_deferred_and_never_part_of_default_import_query(self):
        column = ImportRecord.__table__.c.pdf_bytes
        self.assertIsInstance(column.type, LargeBinary)
        self.assertTrue(ImportRecord.__mapper__.attrs.pdf_bytes.deferred)
        sql = str(select(ImportRecord).compile(dialect=postgresql.dialect()))
        self.assertNotIn("pdf_bytes", sql)
        self.assertIn("file_sha256", sql)

    def test_columns_match_the_reviewed_drawio_model(self):
        from pathlib import Path
        from xml.etree import ElementTree as ET

        path = Path(__file__).resolve().parent.parent / "docs/schema/hisaab-er.drawio"
        cells = ET.parse(path).getroot().findall(".//mxCell")
        for entity, model in (
            ("owner", Owner),
            ("card", Card),
            ("statement", Statement),
            ("import", ImportRecord),
            ("entry", Entry),
        ):
            columns = {
                cell.attrib["id"][len(entity) + 1 :]
                for cell in cells
                if cell.get("parent") == entity
            }
            self.assertEqual(columns, set(model.__table__.columns.keys()))

    def test_amount_is_an_exact_numeric_column(self):
        column = Entry.__table__.c.amount
        self.assertIsInstance(column.type, Numeric)
        self.assertEqual((column.type.precision, column.type.scale), (20, 2))
        self.assertTrue(column.type.asdecimal)

    def test_contribution_amounts_are_exact_positive_decimals(self):
        from decimal import Decimal

        for value in (0.1, 1):
            with self.assertRaises(TypeError):
                Contribution(amount=value)
        for value in (
            "NaN",
            "Infinity",
            "-1.00",
            "0.00",
            "1.001",
            "1000000000000000000.00",
        ):
            with self.assertRaises(ValueError):
                Contribution(amount=Decimal(value))
        self.assertEqual(Contribution(amount=Decimal("0.01")).amount, Decimal("0.01"))

    def test_named_keys_enforce_the_same_owner_and_statement(self):
        self.assertEqual(
            {
                tuple(c.name for c in key.columns)
                for key in Card.__table__.constraints
                if key.__class__.__name__ == "UniqueConstraint"
            },
            {("owner_id", "id")},
        )
        active = next(
            key
            for key in Statement.__table__.foreign_key_constraints
            if key.name == "fk_statements_active_import"
        )
        self.assertEqual(
            tuple(active.column_keys), ("owner_id", "id", "active_import_id")
        )
        self.assertTrue(active.use_alter)
        self.assertEqual(
            tuple(element.target_fullname for element in active.elements),
            (
                "hisaab.imports.owner_id",
                "hisaab.imports.statement_id",
                "hisaab.imports.id",
            ),
        )

    def test_models_do_not_replace_parser_dataclasses(self):
        from core.models import Statement as ParsedStatement

        self.assertIsNot(Statement, ParsedStatement)
        self.assertFalse(hasattr(ParsedStatement, "__table__"))

    def test_ids_are_not_merchant_or_sequence_identities(self):
        for model in (Owner, Card, Statement, ImportRecord, Entry):
            self.assertEqual(
                [column.name for column in model.__table__.primary_key], ["id"]
            )

    def test_amount_validation_rejects_float_and_excess_scale(self):
        from decimal import Decimal

        for amount in (
            1.2,
            Decimal("1.001"),
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
        ):
            with (
                self.subTest(amount=str(amount)),
                self.assertRaises((ValueError, TypeError)),
            ):
                Entry(amount=amount)
        self.assertEqual(Entry(amount=Decimal("123.45")).amount, Decimal("123.45"))
        self.assertIsNone(Entry(amount=None).amount)
