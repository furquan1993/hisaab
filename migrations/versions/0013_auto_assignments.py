"""Learn independent assignments from private history and explicit corrections."""

from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0013_auto_assignments"
down_revision = "0012_funding_query_plan"
branch_labels = depends_on = None
SQL = Path(__file__).parent.parent / "sql"


def upgrade():
    op.create_table(
        "assignment_examples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("hisaab.owners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("merchant_key", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("is_manual", sa.Boolean(), nullable=False),
        sa.Column("entry_id", sa.Uuid()),
        sa.Column("account_id", sa.Uuid()),
        sa.Column("category_id", sa.Uuid()),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "source_key", "kind", name="uq_assignment_examples_source"),
        sa.ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_assignment_examples_entry"),
        sa.ForeignKeyConstraint(["owner_id", "account_id"], ["hisaab.accounts.owner_id", "hisaab.accounts.id"], ondelete="RESTRICT", name="fk_assignment_examples_account"),
        sa.ForeignKeyConstraint(["owner_id", "category_id"], ["hisaab.categories.owner_id", "hisaab.categories.id"], ondelete="RESTRICT", name="fk_assignment_examples_category"),
        sa.CheckConstraint("kind IN ('account','category')", name="ck_assignment_examples_kind"),
        sa.CheckConstraint("direction IN ('debit','credit') OR (is_manual AND direction='unknown')", name="ck_assignment_examples_direction"),
        sa.CheckConstraint("(kind='account' AND category_id IS NULL) OR (kind='category' AND account_id IS NULL)", name="ck_assignment_examples_label"),
        sa.CheckConstraint("is_manual = (entry_id IS NOT NULL)", name="ck_assignment_examples_manual"),
        schema="hisaab",
    )
    op.create_index("ix_assignment_examples_match", "assignment_examples", ["owner_id", "merchant_key", "direction", "kind"], schema="hisaab")
    op.execute((SQL / "0013_auto_assignments.sql").read_text())


def downgrade():
    op.execute("""
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM hisaab.assignment_examples) THEN
        RAISE EXCEPTION 'Assignment learning exists; use a reviewed restore instead of destructive downgrade';
      END IF; END $$;
      DROP TRIGGER assign_selected_source ON hisaab.statements;
      DROP TRIGGER assign_selected_entry ON hisaab.entries;
      DROP FUNCTION hisaab.assign_selected_source(),hisaab.assign_selected_entry();
      DROP FUNCTION hisaab_api.auto_assign_entries(uuid[],uuid);
      DROP FUNCTION hisaab.apply_entry_assignments(uuid,uuid);
      DROP FUNCTION hisaab.assignment_prediction(uuid,text,text,text);
      DROP FUNCTION hisaab_api.save_entry_decision(uuid,integer,jsonb);
      ALTER FUNCTION hisaab.save_entry_decision_without_learning(uuid,integer,jsonb) SET SCHEMA hisaab_api;
      ALTER FUNCTION hisaab_api.save_entry_decision_without_learning(uuid,integer,jsonb) RENAME TO save_entry_decision;
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION hisaab_api.save_entry_decision(uuid,integer,jsonb) TO authenticated;
      END IF; END $$;
    """)
    op.drop_table("assignment_examples", schema="hisaab")
    op.execute("DROP FUNCTION hisaab.merchant_key(text); NOTIFY pgrst,'reload schema'")
