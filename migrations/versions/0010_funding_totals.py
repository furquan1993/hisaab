"""Derived monthly funding totals; no copied obligations or balances."""

from pathlib import Path

from alembic import op

revision = "0010_funding_totals"
down_revision = "0009_reasoned_review"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        (Path(__file__).parent.parent / "sql/0010_funding_totals.sql").read_text()
    )


def downgrade():
    op.execute(
        "DROP VIEW hisaab_api.funding_attention,hisaab_api.funding_totals,hisaab.funding_obligations,hisaab.funding_rows"
    )
    op.execute("NOTIFY pgrst,'reload schema'")
