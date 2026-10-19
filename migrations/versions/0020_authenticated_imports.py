"""Atomic user-authenticated local-parser imports through the Data API."""

from pathlib import Path

from alembic import op

revision = "0020_authenticated_imports"
down_revision = "0019_transaction_contributions"
branch_labels = depends_on = None


def upgrade():
    op.execute((Path(__file__).parent.parent / "sql/0020_authenticated_imports.sql").read_text())


def downgrade():
    op.execute("""
        DROP FUNCTION hisaab_api.import_statement(uuid,jsonb,text);
        DROP FUNCTION hisaab_api.find_pdf_import(uuid,text);
        DROP FUNCTION hisaab.import_summary(uuid,uuid,text);
        NOTIFY pgrst,'reload schema';
    """)
