"""Card-scoped immutable receipts and explicit settlement reconfirmation."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0011_contributions"
down_revision = "0010_funding_totals"
branch_labels = depends_on = None


def upgrade():
    for name in ("contributions", "funding_confirmations"):
        columns = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Uuid(),
                sa.ForeignKey("hisaab.owners.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("card_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("currency", sa.Text(), nullable=False),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("actor_auth_user_id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(
                ["owner_id", "card_id"],
                ["hisaab.cards.owner_id", "hisaab.cards.id"],
                ondelete="RESTRICT",
                name=f"fk_{name}_card",
            ),
            sa.ForeignKeyConstraint(
                ["owner_id", "account_id"],
                ["hisaab.accounts.owner_id", "hisaab.accounts.id"],
                ondelete="RESTRICT",
                name=f"fk_{name}_account",
            ),
            sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=f"ck_{name}_currency"),
            sa.CheckConstraint(
                "month = date_trunc('month',month)::date", name=f"ck_{name}_month"
            ),
        ]
        if name == "contributions":
            columns.extend(
                [
                    sa.Column("amount", sa.Numeric(20, 2), nullable=False),
                    sa.Column("received_on", sa.Date(), nullable=False),
                    sa.Column("note", sa.Text(), nullable=False),
                    sa.Column("applications", sa.JSON(), nullable=False),
                    sa.Column("request", sa.JSON(), nullable=False),
                    sa.CheckConstraint("amount>0", name="ck_contributions_amount"),
                    sa.CheckConstraint(
                        "jsonb_typeof(applications::jsonb)='array' AND jsonb_array_length(applications::jsonb)>0",
                        name="ck_contributions_applications",
                    ),
                ]
            )
        else:
            columns.extend(
                [
                    sa.Column("fingerprint", sa.Text(), nullable=False),
                    sa.Column("reason", sa.Text(), nullable=False),
                ]
            )
        op.create_table(name, *columns, schema="hisaab")
        op.execute(
            f"ALTER TABLE hisaab.{name} ENABLE ROW LEVEL SECURITY; CREATE POLICY browser_read ON hisaab.{name} FOR SELECT USING(owner_id=(SELECT hisaab.current_owner_id()))"
        )
    op.create_index(
        "ix_contributions_scope",
        "contributions",
        ["owner_id", "card_id", "account_id", "currency"],
        schema="hisaab",
    )
    op.create_index(
        "ix_funding_confirmations_scope",
        "funding_confirmations",
        ["owner_id", "card_id", "account_id", "currency", "month", "created_at"],
        schema="hisaab",
    )
    for suffix in ("views", "api"):
        op.execute(
            (
                Path(__file__).parent.parent / f"sql/0011_contribution_{suffix}.sql"
            ).read_text()
        )


def downgrade():
    op.execute("""
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM hisaab.contributions) OR EXISTS(SELECT 1 FROM hisaab.funding_confirmations) THEN
      RAISE EXCEPTION 'Contribution history exists; use a reviewed restore instead of destructive downgrade';
    END IF; END $$;
    DROP FUNCTION IF EXISTS hisaab_api.record_contribution(uuid,uuid,uuid,text,date,text,date,text,text,uuid),
      hisaab_api.confirm_funding(uuid,uuid,text,date,text,text,uuid,date),
      hisaab_api.confirm_funding(uuid,uuid,text,date,text,text,uuid),hisaab_api.funding_preview(uuid,uuid,text,date,uuid);
    DROP FUNCTION hisaab.funding_preview_for_owner(uuid,uuid,uuid,text,date);
    DROP VIEW IF EXISTS hisaab_api.funding_entries,hisaab_api.contributions,hisaab_api.funding_groups,hisaab.funding_balances,hisaab.contribution_applications;
    """)
    op.drop_table("funding_confirmations", schema="hisaab")
    op.drop_table("contributions", schema="hisaab")
    op.execute("NOTIFY pgrst,'reload schema'")
