"""Versioned decisions and immutable audit, separate from imported facts."""

import sqlalchemy as sa
from alembic import op

revision = "0005_entry_decisions"
down_revision = "0004_labels"
branch_labels = depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_entries_owner_id", "entries", ["owner_id", "id"], schema="hisaab"
    )

    def common():
        return [
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
            sa.Column("entry_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        ]

    columns = common()
    columns[-1].server_default = sa.DefaultClause("1")
    op.create_table(
        "entry_decisions",
        *columns,
        sa.Column("category_id", sa.Uuid()),
        sa.Column("account_id", sa.Uuid()),
        sa.Column("overrides", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("acknowledged", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("source_fingerprint", sa.Text()),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_decisions_entry",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "category_id"],
            ["hisaab.categories.owner_id", "hisaab.categories.id"],
            ondelete="RESTRICT",
            name="fk_decisions_category",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "account_id"],
            ["hisaab.accounts.owner_id", "hisaab.accounts.id"],
            ondelete="RESTRICT",
            name="fk_decisions_account",
        ),
        sa.UniqueConstraint("owner_id", "entry_id", name="uq_entry_decisions_entry"),
        sa.CheckConstraint("version>0", name="ck_decisions_version"),
        schema="hisaab",
    )
    op.create_table(
        "decision_events",
        *common(),
        sa.Column("actor_auth_user_id", sa.Uuid()),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_decision_events_entry",
        ),
        sa.UniqueConstraint(
            "owner_id", "entry_id", "version", name="uq_decision_events_version"
        ),
        schema="hisaab",
    )
    for name in ("entry_decisions", "decision_events"):
        op.execute(f"ALTER TABLE hisaab.{name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY browser_read ON hisaab.{name} FOR SELECT USING (owner_id=(SELECT hisaab.current_owner_id()))"
        )
    op.execute("""
        CREATE FUNCTION hisaab.entry_fingerprint(e hisaab.entries) RETURNS text
        LANGUAGE sql IMMUTABLE SET search_path='' AS $$
          SELECT encode(sha256(convert_to(jsonb_build_array(
            e.transaction_date,e.transaction_time,e.description,e.amount::text,e.direction,
            e.currency,e.entry_type,e.section,e.raw_date,e.raw_time,e.raw_amount,
            e.source_page,e.source_bbox::jsonb,e.source_raw_text,e.issues::jsonb
          )::text,'UTF8')),'hex')
        $$;
        REVOKE ALL ON FUNCTION hisaab.entry_fingerprint(hisaab.entries) FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON hisaab.entry_decisions,hisaab.decision_events FROM anon;
            REVOKE ALL ON FUNCTION hisaab.entry_fingerprint(hisaab.entries) FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON hisaab.entry_decisions,hisaab.decision_events FROM authenticated;
            GRANT SELECT ON hisaab.entry_decisions,hisaab.decision_events TO authenticated;
            GRANT EXECUTE ON FUNCTION hisaab.entry_fingerprint(hisaab.entries) TO authenticated;
          END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP FUNCTION hisaab.entry_fingerprint(hisaab.entries)")
    op.drop_table("decision_events", schema="hisaab")
    op.drop_table("entry_decisions", schema="hisaab")
    op.drop_constraint("uq_entries_owner_id", "entries", schema="hisaab")
