"""Explore spending with independent, owner-scoped trip groups."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "0015_spending_groups"
down_revision = "0014_statement_balances"
branch_labels = depends_on = None
SQL = Path(__file__).parent.parent / "sql"


def common():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("hisaab.owners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def upgrade():
    op.create_table(
        "spending_groups", *common(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_spending_groups_owner_id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_spending_groups_name"),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 120", name="ck_spending_groups_name"),
        sa.CheckConstraint("version > 0", name="ck_spending_groups_version"),
        schema="hisaab",
    )
    op.create_table(
        "spending_assignments", *common(),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid()),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.UniqueConstraint("owner_id", "entry_id", name="uq_spending_assignments_entry"),
        sa.ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_spending_assignments_entry"),
        sa.ForeignKeyConstraint(["owner_id", "group_id"], ["hisaab.spending_groups.owner_id", "hisaab.spending_groups.id"], ondelete="RESTRICT", name="fk_spending_assignments_group"),
        sa.CheckConstraint("version > 0", name="ck_spending_assignments_version"),
        schema="hisaab",
    )
    op.create_table(
        "spending_events", *common(),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_auth_user_id", sa.Uuid()),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_spending_events_entry"),
        sa.UniqueConstraint("owner_id", "entry_id", "version", name="uq_spending_events_version"),
        schema="hisaab",
    )
    for table in ("spending_groups", "spending_assignments", "spending_events"):
        op.execute(f"ALTER TABLE hisaab.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY browser_read ON hisaab.{table} FOR SELECT USING (owner_id=(SELECT hisaab.current_owner_id()))")
    op.execute((SQL / "0015_spending_groups.sql").read_text())


def downgrade():
    if not op.get_context().as_sql:
        if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM hisaab.spending_groups) OR EXISTS(SELECT 1 FROM hisaab.spending_assignments) OR EXISTS(SELECT 1 FROM hisaab.spending_events)")):
            raise CommandError("Spending groups or history exist. Export and review them before downgrading.")
    op.execute("DROP VIEW hisaab_api.spending_entries, hisaab_api.spending_groups")
    op.execute("DROP FUNCTION hisaab_api.save_spending_group(text,uuid,integer,boolean,uuid), hisaab_api.assign_spending_group(uuid,jsonb,uuid)")
    for table in ("spending_events", "spending_assignments", "spending_groups"):
        op.drop_table(table, schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
