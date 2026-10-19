"""Explicit full-transaction contribution applications, retaining old receipts."""

from pathlib import Path
from alembic import op

revision = "0019_transaction_contributions"
down_revision = "0018_card_management"
branch_labels = depends_on = None


def upgrade():
    op.execute((Path(__file__).parent.parent / "sql/0019_transaction_contributions.sql").read_text())


def downgrade():
    op.execute("""
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM hisaab.contributions c,
        LATERAL jsonb_array_elements(c.applications::jsonb) a WHERE a ? 'entries') THEN
        RAISE EXCEPTION 'Transaction contribution history exists; use a reviewed restore';
      END IF;
    END $$;
    DROP FUNCTION hisaab_api.record_transaction_contribution(uuid,uuid,uuid,text,date,uuid[],date,text,text,uuid);
    DROP VIEW hisaab_api.funding_transaction_entries;
    NOTIFY pgrst,'reload schema';
    """)
