"""Personal transaction descriptions, independent of financial decisions."""
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

revision = "0016_friendly_descriptions"
down_revision = "0015_spending_groups"
branch_labels = depends_on = None
SQL = Path(__file__).parent.parent / "sql"


def upgrade():
    op.create_table(
        "entry_descriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("hisaab.owners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actor_auth_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_entry_descriptions_entry"),
        sa.UniqueConstraint("owner_id", "entry_id", "version", name="uq_entry_descriptions_version"),
        sa.CheckConstraint("version>0", name="ck_entry_descriptions_version"),
        sa.CheckConstraint("description IS NULL OR length(btrim(description)) BETWEEN 1 AND 500", name="ck_entry_descriptions_text"),
        schema="hisaab",
    )
    op.execute((SQL / "0016_friendly_descriptions.sql").read_text())


def downgrade():
    if not op.get_context().as_sql and op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM hisaab.entry_descriptions)")):
        raise CommandError("Description history exists; use a reviewed restore instead of discarding it")
    # Keep appended API columns during rollback so dependent financial views retain
    # their definitions, permissions and fingerprints.
    op.execute((SQL / "0016_friendly_descriptions_rollback.sql").read_text())
    op.drop_table("entry_descriptions", schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
