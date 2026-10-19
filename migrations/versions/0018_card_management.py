"""Owner-scoped card creation and versioned editing."""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "0018_card_management"
down_revision = "0017_account_deletion"
branch_labels = depends_on = None


def upgrade():
    op.add_column("cards", sa.Column("version", sa.Integer(), nullable=False, server_default="1"), schema="hisaab")
    op.create_check_constraint("ck_cards_version", "cards", "version > 0", schema="hisaab")
    op.execute((Path(__file__).parent.parent / "sql/0018_card_management.sql").read_text())


def downgrade():
    op.execute("DROP FUNCTION hisaab_api.save_card(uuid,text,text,text,uuid,integer)")
    op.execute("DROP VIEW hisaab_api.cards")
    op.drop_constraint("ck_cards_version", "cards", schema="hisaab")
    op.drop_column("cards", "version", schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
