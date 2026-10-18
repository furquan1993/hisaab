"""create five entity schema

Revision ID: 0001_initial_schema
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Keep financial tables outside Supabase's public API schema.
    op.execute(sa.schema.CreateSchema("hisaab"))
    op.execute(sa.text("REVOKE ALL ON SCHEMA hisaab FROM PUBLIC"))
    op.create_table(
        "owners",
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_owners")),
        schema="hisaab",
    )
    op.create_table(
        "cards",
        sa.Column("bank", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "last_four IS NULL OR length(last_four) = 4", name="ck_cards_last_four"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["hisaab.owners.id"],
            name=op.f("fk_cards_owner_id_owners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cards")),
        sa.UniqueConstraint("owner_id", "id", name="uq_cards_owner_id"),
        schema="hisaab",
    )
    op.create_table(
        "statements",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("statement_date", sa.Date(), nullable=True),
        sa.Column("active_import_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "card_id"],
            ["hisaab.cards.owner_id", "hisaab.cards.id"],
            name="fk_statements_card",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["hisaab.owners.id"],
            name=op.f("fk_statements_owner_id_owners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statements")),
        sa.UniqueConstraint(
            "owner_id", "card_id", "id", name="uq_statements_owner_card_id"
        ),
        sa.UniqueConstraint("owner_id", "id", name="uq_statements_owner_id"),
        schema="hisaab",
    )
    op.create_table(
        "imports",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("pdf_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_statement_date", sa.Date(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("extractor_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'rejected')",
            name="ck_imports_review_status",
        ),
        sa.CheckConstraint(
            "(pdf_bytes IS NOT NULL AND pdf_deleted_at IS NULL) OR (pdf_bytes IS NULL AND pdf_deleted_at IS NOT NULL)",
            name="ck_imports_pdf_lifecycle",
        ),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_imports_file_size"),
        sa.CheckConstraint("length(file_sha256) = 64", name="ck_imports_sha256_length"),
        sa.CheckConstraint("page_count > 0", name="ck_imports_page_count"),
        sa.CheckConstraint(
            "pdf_bytes IS NULL OR length(pdf_bytes) = file_size_bytes",
            name="ck_imports_pdf_size",
        ),
        sa.CheckConstraint("schema_version > 0", name="ck_imports_schema_version"),
        sa.ForeignKeyConstraint(
            ["owner_id", "card_id", "statement_id"],
            [
                "hisaab.statements.owner_id",
                "hisaab.statements.card_id",
                "hisaab.statements.id",
            ],
            name="fk_imports_statement",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "card_id"],
            ["hisaab.cards.owner_id", "hisaab.cards.id"],
            name="fk_imports_card",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["hisaab.owners.id"],
            name=op.f("fk_imports_owner_id_owners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imports")),
        sa.UniqueConstraint(
            "owner_id", "card_id", "file_sha256", name="uq_imports_owner_card_sha256"
        ),
        sa.UniqueConstraint("owner_id", "id", name="uq_imports_owner_id"),
        sa.UniqueConstraint(
            "owner_id", "statement_id", "id", name="uq_imports_owner_statement_id"
        ),
        schema="hisaab",
    )
    op.create_table(
        "entries",
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("transaction_time", sa.Time(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("direction", sa.String(length=6), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("raw_date", sa.Text(), nullable=False),
        sa.Column("raw_time", sa.Text(), nullable=False),
        sa.Column("raw_amount", sa.Text(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("source_bbox", sa.JSON(), nullable=False),
        sa.Column("source_raw_text", sa.Text(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('debit', 'credit')",
            name="ck_entries_direction",
        ),
        sa.CheckConstraint(
            "entry_type IN ('purchase','payment','refund','cashback','fee','interest','tax','reversal','unknown')",
            name="ck_entries_entry_type",
        ),
        sa.CheckConstraint(
            "amount IS NULL OR (amount >= 0 AND amount < 1000000000000000000)",
            name="ck_entries_amount",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR length(currency) = 3", name="ck_entries_currency"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_entries_sequence"),
        sa.CheckConstraint("source_page > 0", name="ck_entries_source_page"),
        sa.ForeignKeyConstraint(
            ["owner_id", "import_id"],
            ["hisaab.imports.owner_id", "hisaab.imports.id"],
            name="fk_entries_import",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["hisaab.owners.id"],
            name=op.f("fk_entries_owner_id_owners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entries")),
        sa.UniqueConstraint("import_id", "sequence", name="uq_entries_import_sequence"),
        schema="hisaab",
    )
    op.create_index(
        "ix_entries_owner_import",
        "entries",
        ["owner_id", "import_id"],
        unique=False,
        schema="hisaab",
    )
    # Break the statement/import DDL cycle explicitly; autogeneration misses this step.
    op.create_foreign_key(
        "fk_statements_active_import",
        "statements",
        "imports",
        ["owner_id", "id", "active_import_id"],
        ["owner_id", "statement_id", "id"],
        source_schema="hisaab",
        referent_schema="hisaab",
        ondelete="RESTRICT",
    )
    # Default deny for non-owner roles. This is not per-user authentication.
    for table in ("owners", "cards", "statements", "imports", "entries"):
        op.execute(sa.text(f"ALTER TABLE hisaab.{table} ENABLE ROW LEVEL SECURITY"))


def downgrade():
    # Destructive: back up application data before an explicitly requested downgrade.
    op.drop_constraint(
        "fk_statements_active_import", "statements", schema="hisaab", type_="foreignkey"
    )
    op.drop_index("ix_entries_owner_import", table_name="entries", schema="hisaab")
    op.drop_table("entries", schema="hisaab")
    op.drop_table("imports", schema="hisaab")
    op.drop_table("statements", schema="hisaab")
    op.drop_table("cards", schema="hisaab")
    op.drop_table("owners", schema="hisaab")
    # No CASCADE: refuse to remove a namespace containing unexpected objects.
    op.execute(sa.schema.DropSchema("hisaab"))
