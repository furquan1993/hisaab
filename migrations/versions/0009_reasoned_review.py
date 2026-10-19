"""Audited corrections and independent statement coverage/date acknowledgements."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0009_reasoned_review"
down_revision = "0008_revision_api"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "import_reviews",
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
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_import_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.Text(), nullable=False),
        sa.Column("acknowledged", sa.JSON(), nullable=False),
        sa.Column("statement_date_override", sa.Date()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_auth_user_id", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["owner_id", "import_id"],
            ["hisaab.imports.owner_id", "hisaab.imports.id"],
            ondelete="RESTRICT",
            name="fk_import_reviews_root",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "reviewed_import_id"],
            ["hisaab.imports.owner_id", "hisaab.imports.id"],
            ondelete="RESTRICT",
            name="fk_import_reviews_source",
        ),
        sa.UniqueConstraint(
            "owner_id", "import_id", "version", name="uq_import_reviews_version"
        ),
        sa.CheckConstraint("version>0", name="ck_import_reviews_version"),
        schema="hisaab",
    )
    op.execute(
        "ALTER TABLE hisaab.import_reviews ENABLE ROW LEVEL SECURITY; CREATE POLICY browser_read ON hisaab.import_reviews FOR SELECT USING(owner_id=(SELECT hisaab.current_owner_id()))"
    )
    for suffix in ("helpers", "entry", "import", "views"):
        op.execute(
            (
                Path(__file__).resolve().parent.parent
                / "sql"
                / f"0009_review_{suffix}.sql"
            ).read_text(encoding="utf-8")
        )
    op.execute("""
      REVOKE ALL ON hisaab.import_reviews,hisaab.import_review_data,hisaab.reviewed_entry_data,hisaab_api.import_review_history FROM PUBLIC;
      DO $$ DECLARE f record; role_name text; BEGIN
       FOR f IN SELECT p.oid::regprocedure AS signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE (n.nspname='hisaab' AND p.proname IN ('issue_key','critical_issue','coverage_fingerprint','effective_values','unresolved_issues'))
           OR (n.nspname='hisaab_api' AND p.proname IN ('review_entry','review_import')) LOOP
         EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
         FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
           IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.signature,role_name); END IF;
         END LOOP;
       END LOOP;
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
         REVOKE ALL ON hisaab.import_reviews,hisaab.import_review_data,hisaab.reviewed_entry_data,hisaab_api.import_review_history FROM anon;
       END IF;
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
         REVOKE ALL ON hisaab.import_reviews,hisaab.import_review_data,hisaab.reviewed_entry_data,hisaab_api.import_review_history FROM authenticated;
         GRANT SELECT ON hisaab.import_reviews,hisaab.import_review_data,hisaab.reviewed_entry_data,hisaab_api.import_review_history TO authenticated;
         GRANT EXECUTE ON FUNCTION hisaab.issue_key(jsonb),hisaab.critical_issue(text),hisaab.coverage_fingerprint(text,integer,date,jsonb),
           hisaab.effective_values(hisaab.entries,hisaab.entry_decisions),hisaab.unresolved_issues(jsonb,jsonb,jsonb),
           hisaab_api.review_entry(uuid,integer,jsonb,jsonb,text,boolean),hisaab_api.review_import(uuid,integer,jsonb,text,text) TO authenticated;
       END IF;
      END $$;
      NOTIFY pgrst,'reload schema';
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM hisaab.import_reviews) OR EXISTS(SELECT 1 FROM hisaab.entry_decisions WHERE source_fingerprint IS NOT NULL) THEN
        RAISE EXCEPTION 'Review history exists; use a reviewed restore instead of destructive downgrade';
      END IF; END $$;
      DROP VIEW hisaab_api.entries,hisaab_api.sources,hisaab_api.import_review_history;
      DROP VIEW hisaab.reviewed_entry_data,hisaab.import_review_data;
      CREATE VIEW hisaab_api.entries WITH(security_invoker=true) AS
       SELECT e.*,hisaab.logical_entry_id(e.id) AS logical_entry_id,coalesce(d.version,0) AS decision_version,
        d.category_id,c.name AS category_name,d.account_id,a.name AS account_name,coalesce(d.overrides::jsonb,'{}'::jsonb) AS overrides,
        coalesce(d.acknowledged::jsonb,'[]'::jsonb) AS acknowledged,d.source_fingerprint,d.updated_at AS decision_updated_at
       FROM hisaab.extracted_entries e LEFT JOIN hisaab.entry_decisions d ON d.entry_id=hisaab.logical_entry_id(e.id) AND d.owner_id=hisaab.current_owner_id()
       LEFT JOIN hisaab.categories c ON c.id=d.category_id AND c.owner_id=d.owner_id
       LEFT JOIN hisaab.accounts a ON a.id=d.account_id AND a.owner_id=d.owner_id;
      CREATE VIEW hisaab_api.sources WITH(security_invoker=true) AS
       SELECT i.id,i.statement_id,c.label AS card_label,c.bank,s.statement_date,i.source_import_id,
        i.source_filename,i.file_sha256,i.parsed_statement_date,i.page_count,i.parser_version,i.extractor_version,
        i.issues::jsonb AS issues,hisaab.import_state(i.id) AS state,i.created_at,
        (SELECT count(*) FROM hisaab.entries e WHERE e.import_id=i.id AND e.owner_id=i.owner_id) AS entry_count
       FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
       JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id;
      REVOKE ALL ON hisaab_api.entries,hisaab_api.sources FROM PUBLIC;
      DO $$ BEGIN
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON hisaab_api.entries,hisaab_api.sources FROM anon; END IF;
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON hisaab_api.entries,hisaab_api.sources FROM authenticated; GRANT SELECT ON hisaab_api.entries,hisaab_api.sources TO authenticated;
       END IF;
      END $$;
      DROP FUNCTION hisaab_api.review_entry(uuid,integer,jsonb,jsonb,text,boolean),hisaab_api.review_import(uuid,integer,jsonb,text,text);
      DROP FUNCTION hisaab.unresolved_issues(jsonb,jsonb,jsonb),hisaab.effective_values(hisaab.entries,hisaab.entry_decisions),hisaab.coverage_fingerprint(text,integer,date,jsonb),hisaab.critical_issue(text),hisaab.issue_key(jsonb);
    """)
    op.drop_table("import_reviews", schema="hisaab")
