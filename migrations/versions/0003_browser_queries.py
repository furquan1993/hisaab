"""Read-only API views and explicit original retrieval.

https://supabase.com/docs/guides/database/postgres/row-level-security#views
https://www.postgresql.org/docs/17/functions-binarystring.html
"""

from alembic import op

revision = "0003_browser_queries"
down_revision = "0002_browser_identity"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        CREATE VIEW hisaab_api.entries WITH (security_invoker = true) AS
        SELECT e.id, e.import_id, s.id AS statement_id, c.label AS card_label, c.bank,
               s.statement_date, e.transaction_date, e.description, e.amount::text AS amount,
               e.direction, e.currency, e.entry_type, e.sequence,
               (s.active_import_id IS NOT DISTINCT FROM i.id) AS is_selected,
               (s.active_import_id IS DISTINCT FROM i.id OR
                e.transaction_date IS NULL OR s.statement_date IS NULL OR
                jsonb_array_length(e.issues::jsonb) > 0 OR
                jsonb_array_length(i.issues::jsonb) > 0) AS needs_review,
               e.issues::jsonb AS entry_issues, i.issues::jsonb AS import_issues,
               i.review_status
        FROM hisaab.entries e
        JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
        JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
        JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id;
        CREATE VIEW hisaab_api.entry_evidence WITH (security_invoker = true) AS
        SELECT e.id, e.import_id, e.raw_date, e.raw_time, e.raw_amount,
               e.source_page, e.source_bbox, e.source_raw_text, e.section,
               i.source_filename, i.file_sha256, i.pdf_deleted_at,
               i.page_count, i.parser_version, i.extractor_version
        FROM hisaab.entries e
        JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id;
        REVOKE ALL ON hisaab_api.entries, hisaab_api.entry_evidence FROM PUBLIC;
    """)
    # Only this explicit function can read bytes. Ownership is checked even though
    # its owner bypasses RLS; qualified names and fixed search_path prevent shadowing.
    op.execute("""
        CREATE FUNCTION hisaab_api.original_pdf(p_import_id uuid) RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE source hisaab.imports;
        BEGIN
            SELECT * INTO source FROM hisaab.imports
            WHERE id=p_import_id AND owner_id=hisaab.current_owner_id();
            IF NOT FOUND OR source.pdf_bytes IS NULL THEN RETURN NULL; END IF;
            IF pg_catalog.encode(pg_catalog.sha256(source.pdf_bytes), 'hex') <> source.file_sha256 THEN
                RAISE EXCEPTION 'Original integrity check failed' USING ERRCODE='XX001';
            END IF;
            RETURN pg_catalog.jsonb_build_object(
                'sha256', source.file_sha256,
                'content_base64', pg_catalog.encode(source.pdf_bytes, 'base64'));
        END $$;
        REVOKE ALL ON FUNCTION hisaab_api.original_pdf(uuid) FROM PUBLIC;
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                REVOKE ALL ON hisaab_api.entries, hisaab_api.entry_evidence FROM anon;
                REVOKE ALL ON FUNCTION hisaab_api.original_pdf(uuid) FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE ALL ON hisaab_api.entries, hisaab_api.entry_evidence FROM authenticated;
                GRANT SELECT ON hisaab.cards, hisaab.statements, hisaab.entries TO authenticated;
                GRANT SELECT (
                    id, owner_id, card_id, statement_id, source_filename, file_sha256,
                    file_size_bytes, pdf_deleted_at, parsed_statement_date, page_count,
                    parser_version, extractor_version, schema_version, review_status, issues, created_at
                ) ON hisaab.imports TO authenticated;
                GRANT SELECT ON hisaab_api.entries, hisaab_api.entry_evidence TO authenticated;
                GRANT EXECUTE ON FUNCTION hisaab_api.original_pdf(uuid) TO authenticated;
            END IF;
        END $$;
        NOTIFY pgrst, 'reload schema';
    """)


def downgrade():
    op.execute("""
        DROP FUNCTION hisaab_api.original_pdf(uuid);
        DROP VIEW hisaab_api.entry_evidence;
        DROP VIEW hisaab_api.entries;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE SELECT ON hisaab.cards, hisaab.statements, hisaab.entries FROM authenticated;
                REVOKE SELECT (
                    id, owner_id, card_id, statement_id, source_filename, file_sha256,
                    file_size_bytes, pdf_deleted_at, parsed_statement_date, page_count,
                    parser_version, extractor_version, schema_version, review_status, issues, created_at
                ) ON hisaab.imports FROM authenticated;
            END IF;
        END $$;
    """)
