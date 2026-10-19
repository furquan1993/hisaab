"""Permanent account removal with transaction preview and retained audit history."""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "0017_account_deletion"
down_revision = "0016_friendly_descriptions"
branch_labels = depends_on = None


def upgrade():
    # Keep a tombstone for immutable reconciliation receipts and historical IDs.
    op.add_column("accounts", sa.Column("deleted_at", sa.DateTime(timezone=True)), schema="hisaab")
    op.execute((Path(__file__).parent.parent / "sql/0017_account_deletion.sql").read_text())


def downgrade():
    op.execute("""
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM hisaab.accounts WHERE deleted_at IS NOT NULL) THEN
      RAISE EXCEPTION 'Deleted accounts exist; use a reviewed restore instead of resurrecting them';
    END IF; END $$;
    DROP FUNCTION hisaab_api.delete_account(uuid,text,uuid);
    DROP FUNCTION hisaab_api.preview_account_deletion(uuid,uuid);
    DROP FUNCTION hisaab.account_deletion_preview(uuid,uuid);
    DROP TRIGGER deleted_account_guard ON hisaab.accounts;
    DROP FUNCTION hisaab.guard_deleted_account();
    CREATE OR REPLACE VIEW hisaab_api.labels WITH (security_invoker=true) AS
      SELECT id,'category'::text AS kind,name,is_archived,version FROM hisaab.categories
      UNION ALL SELECT id,'account',name,is_archived,version FROM hisaab.accounts;
    """)
    op.drop_column("accounts", "deleted_at", schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
