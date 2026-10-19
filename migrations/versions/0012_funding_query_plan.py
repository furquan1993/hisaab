"""Reuse owner-scoped funding evidence instead of repeatedly expanding views."""

from pathlib import Path

from alembic import op

revision = "0012_funding_query_plan"
down_revision = "0011_contributions"
branch_labels = depends_on = None
SQL = Path(__file__).parent.parent / "sql"


def upgrade():
    op.execute((SQL / "0012_funding_query_plan.sql").read_text())


def downgrade():
    # Preserve the deployed definitions of earlier revisions and their grants.
    for filename, name in (
        ("0010_funding_totals.sql", "hisaab.funding_obligations"),
        ("0011_contribution_views.sql", "hisaab.funding_balances"),
    ):
        source = (SQL / filename).read_text()
        start = source.index(f"CREATE VIEW {name} ")
        end = source.index(";", start) + 1
        op.execute(
            source[start:end].replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1)
        )
    op.execute("NOTIFY pgrst,'reload schema'")
