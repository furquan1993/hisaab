"""Candidate source versions share retained originals and bind logical identities."""

import sqlalchemy as sa
from alembic import op

revision = "0007_revision_schema"
down_revision = "0006_assignment_api"
branch_labels = depends_on = None


def upgrade():
    op.add_column("imports", sa.Column("source_import_id", sa.Uuid()), schema="hisaab")
    op.drop_constraint("uq_imports_owner_card_sha256", "imports", schema="hisaab")
    op.create_index(
        "uq_imports_owner_card_sha256",
        "imports",
        ["owner_id", "card_id", "file_sha256"],
        unique=True,
        schema="hisaab",
        postgresql_where=sa.text("source_import_id IS NULL"),
    )
    op.create_unique_constraint(
        "uq_imports_source_file",
        "imports",
        ["owner_id", "card_id", "statement_id", "file_sha256", "id"],
        schema="hisaab",
    )
    op.create_foreign_key(
        "fk_imports_source_file",
        "imports",
        "imports",
        ["owner_id", "card_id", "statement_id", "file_sha256", "source_import_id"],
        ["owner_id", "card_id", "statement_id", "file_sha256", "id"],
        source_schema="hisaab",
        referent_schema="hisaab",
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_imports_source_file",
        "imports",
        "source_import_id IS NULL OR source_import_id<>id",
        schema="hisaab",
    )
    op.drop_constraint("ck_imports_pdf_lifecycle", "imports", schema="hisaab")
    op.create_check_constraint(
        "ck_imports_pdf_lifecycle",
        "imports",
        "(source_import_id IS NULL AND ((pdf_bytes IS NOT NULL AND pdf_deleted_at IS NULL) OR (pdf_bytes IS NULL AND pdf_deleted_at IS NOT NULL))) OR (source_import_id IS NOT NULL AND pdf_bytes IS NULL AND pdf_deleted_at IS NULL)",
        schema="hisaab",
    )
    op.create_unique_constraint(
        "uq_entries_owner_import_id",
        "entries",
        ["owner_id", "import_id", "id"],
        schema="hisaab",
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
        ]

    op.create_table(
        "parser_revisions",
        *common(),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("base_import_id", sa.Uuid()),
        sa.Column("candidate_import_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("reviewed_mapping", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("actor_auth_user_id", sa.Uuid()),
        sa.UniqueConstraint("owner_id", "id", name="uq_revisions_owner_id"),
        sa.UniqueConstraint(
            "owner_id",
            "candidate_import_id",
            "version",
            name="uq_revisions_candidate_version",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "statement_id", "candidate_import_id"],
            [
                "hisaab.imports.owner_id",
                "hisaab.imports.statement_id",
                "hisaab.imports.id",
            ],
            ondelete="RESTRICT",
            name="fk_revisions_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "statement_id", "base_import_id"],
            [
                "hisaab.imports.owner_id",
                "hisaab.imports.statement_id",
                "hisaab.imports.id",
            ],
            ondelete="RESTRICT",
            name="fk_revisions_base",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected')", name="ck_revisions_status"
        ),
        sa.CheckConstraint("version>0", name="ck_revisions_version"),
        schema="hisaab",
    )
    op.create_table(
        "entry_links",
        *common(),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("logical_entry_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint("owner_id", "entry_id", name="uq_entry_links_entry"),
        sa.UniqueConstraint(
            "import_id", "logical_entry_id", name="uq_entry_links_logical"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "import_id", "entry_id"],
            [
                "hisaab.entries.owner_id",
                "hisaab.entries.import_id",
                "hisaab.entries.id",
            ],
            ondelete="RESTRICT",
            name="fk_entry_links_source",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "logical_entry_id"],
            ["hisaab.entries.owner_id", "hisaab.entries.id"],
            ondelete="RESTRICT",
            name="fk_entry_links_logical",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "revision_id"],
            ["hisaab.parser_revisions.owner_id", "hisaab.parser_revisions.id"],
            ondelete="RESTRICT",
            name="fk_entry_links_revision",
        ),
        schema="hisaab",
    )
    for table in ("parser_revisions", "entry_links"):
        op.execute(f"ALTER TABLE hisaab.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY browser_read ON hisaab.{table} FOR SELECT USING (owner_id=(SELECT hisaab.current_owner_id()))"
        )
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON hisaab.parser_revisions,hisaab.entry_links FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON hisaab.parser_revisions,hisaab.entry_links FROM authenticated;
            GRANT SELECT ON hisaab.parser_revisions,hisaab.entry_links TO authenticated;
            GRANT SELECT(source_import_id) ON hisaab.imports TO authenticated;
          END IF;
        END $$;
    """)


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM hisaab.parser_revisions) OR EXISTS(SELECT 1 FROM hisaab.imports WHERE source_import_id IS NOT NULL) THEN
          RAISE EXCEPTION 'Revision history exists; use a reviewed restore instead of destructive downgrade';
        END IF;
    END $$""")
    op.drop_table("entry_links", schema="hisaab")
    op.drop_table("parser_revisions", schema="hisaab")
    op.drop_constraint("uq_entries_owner_import_id", "entries", schema="hisaab")
    op.drop_constraint("ck_imports_source_file", "imports", schema="hisaab")
    op.drop_constraint("fk_imports_source_file", "imports", schema="hisaab")
    op.drop_constraint("uq_imports_source_file", "imports", schema="hisaab")
    op.drop_constraint("ck_imports_pdf_lifecycle", "imports", schema="hisaab")
    op.create_check_constraint(
        "ck_imports_pdf_lifecycle",
        "imports",
        "(pdf_bytes IS NOT NULL AND pdf_deleted_at IS NULL) OR (pdf_bytes IS NULL AND pdf_deleted_at IS NOT NULL)",
        schema="hisaab",
    )
    op.drop_index("uq_imports_owner_card_sha256", table_name="imports", schema="hisaab")
    op.create_unique_constraint(
        "uq_imports_owner_card_sha256",
        "imports",
        ["owner_id", "card_id", "file_sha256"],
        schema="hisaab",
    )
    op.drop_column("imports", "source_import_id", schema="hisaab")
