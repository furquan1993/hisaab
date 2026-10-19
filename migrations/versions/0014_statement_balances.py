"""Keep printed statement balances separate from transaction spending."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "0014_statement_balances"
down_revision = "0013_auto_assignments"
branch_labels = depends_on = None
SQL = Path(__file__).parent.parent / "sql"


def upgrade():
    op.add_column(
        "imports",
        sa.Column("printed_balance", sa.JSON(none_as_null=True), nullable=True),
        schema="hisaab",
    )
    op.execute((SQL / "0014_statement_balances.sql").read_text())


def downgrade():
    # Do not silently discard captured statement evidence.
    if not op.get_context().as_sql:
        captured = op.get_bind().scalar(sa.text(
            "SELECT EXISTS(SELECT 1 FROM hisaab.imports WHERE printed_balance IS NOT NULL)"
        ))
        if captured:
            raise CommandError(
                "Cannot discard captured statement balances. "
                "Export and review them before downgrading."
            )
    op.execute("DROP VIEW hisaab_api.statement_bills")
    op.drop_column("imports", "printed_balance", schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
