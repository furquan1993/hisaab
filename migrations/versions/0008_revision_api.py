"""Reviewable revision comparisons and atomic acceptance; never overwrite evidence."""

from pathlib import Path

from alembic import op

revision = "0008_revision_api"
down_revision = "0007_revision_schema"
branch_labels = depends_on = None


def upgrade():
    for suffix in ("plan", "accept", "views"):
        op.execute(
            (
                Path(__file__).resolve().parent.parent
                / "sql"
                / f"0008_revision_{suffix}.sql"
            ).read_text(encoding="utf-8")
        )
    op.execute("""
      REVOKE ALL ON hisaab.all_extracted_entries,hisaab_api.revision_entries,hisaab_api.sources,hisaab_api.revisions FROM PUBLIC;
      DO $$ DECLARE f record; role_name text; BEGIN
       FOR f IN SELECT p.oid::regprocedure AS signature,n.nspname,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE (n.nspname='hisaab' AND p.proname IN ('import_evidence_hash','revision_plan','prepare_revision_for_owner','accept_revision_for_owner','reject_revision_for_owner','import_state'))
           OR (n.nspname='hisaab_api' AND p.proname IN ('prepare_revision','accept_revision','reject_revision')) LOOP
         EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
         FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
           IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
             EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.signature,role_name);
           END IF;
         END LOOP;
       END LOOP;
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
         REVOKE ALL ON hisaab.all_extracted_entries,hisaab_api.revision_entries,hisaab_api.sources,hisaab_api.revisions FROM anon;
       END IF;
       IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
         REVOKE ALL ON hisaab.all_extracted_entries,hisaab_api.revision_entries,hisaab_api.sources,hisaab_api.revisions FROM authenticated;
         GRANT SELECT ON hisaab.all_extracted_entries,hisaab_api.revision_entries,hisaab_api.sources,hisaab_api.revisions TO authenticated;
         GRANT EXECUTE ON FUNCTION hisaab.import_state(uuid),hisaab_api.prepare_revision(uuid),hisaab_api.accept_revision(uuid,jsonb,jsonb,text,boolean),hisaab_api.reject_revision(uuid,text) TO authenticated;
       END IF;
      END $$;
      NOTIFY pgrst,'reload schema';
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN IF EXISTS(SELECT 1 FROM hisaab.parser_revisions) THEN
        RAISE EXCEPTION 'Revision history exists; use a reviewed restore instead of destructive downgrade';
      END IF; END $$;
      DROP FUNCTION hisaab_api.prepare_revision(uuid),hisaab_api.accept_revision(uuid,jsonb,jsonb,text,boolean),hisaab_api.reject_revision(uuid,text);
      DROP VIEW hisaab_api.revision_entries,hisaab_api.sources,hisaab_api.revisions;
      CREATE OR REPLACE VIEW hisaab.extracted_entries WITH (security_invoker=true) AS
      SELECT e.id,e.import_id,s.id AS statement_id,c.label AS card_label,c.bank,s.statement_date,e.transaction_date,e.description,
        e.amount::text AS amount,e.direction,e.currency,e.entry_type,e.sequence,
        (s.active_import_id IS NOT DISTINCT FROM i.id) AS is_selected,
        (s.active_import_id IS DISTINCT FROM i.id OR e.transaction_date IS NULL OR s.statement_date IS NULL OR
          jsonb_array_length(e.issues::jsonb)>0 OR jsonb_array_length(i.issues::jsonb)>0) AS needs_review,
        e.issues::jsonb AS entry_issues,i.issues::jsonb AS import_issues,i.review_status
      FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
      JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
      JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id;
      DROP VIEW hisaab.all_extracted_entries;
      CREATE OR REPLACE VIEW hisaab_api.entry_evidence WITH (security_invoker=true) AS
      SELECT e.id,e.import_id,e.raw_date,e.raw_time,e.raw_amount,e.source_page,e.source_bbox,e.source_raw_text,e.section,
        i.source_filename,i.file_sha256,i.pdf_deleted_at,i.page_count,i.parser_version,i.extractor_version
      FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id;
      CREATE OR REPLACE FUNCTION hisaab_api.original_pdf(p_import_id uuid) RETURNS jsonb
      LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
      DECLARE source hisaab.imports; BEGIN
       SELECT * INTO source FROM hisaab.imports WHERE id=p_import_id AND owner_id=hisaab.current_owner_id();
       IF NOT FOUND OR source.pdf_bytes IS NULL THEN RETURN NULL; END IF;
       IF encode(sha256(source.pdf_bytes),'hex')<>source.file_sha256 THEN
         RAISE EXCEPTION 'Original integrity check failed' USING ERRCODE='XX001';
       END IF;
       RETURN jsonb_build_object('sha256',source.file_sha256,'content_base64',encode(source.pdf_bytes,'base64'));
      END $$;
      CREATE OR REPLACE FUNCTION hisaab.logical_entry_id(p_id uuid) RETURNS uuid LANGUAGE sql IMMUTABLE SET search_path='' AS $$ SELECT p_id $$;
      DROP FUNCTION hisaab.accept_revision_for_owner(uuid,uuid,jsonb,jsonb,text,boolean),hisaab.reject_revision_for_owner(uuid,uuid,text),hisaab.prepare_revision_for_owner(uuid,uuid);
      DROP FUNCTION hisaab.revision_plan(uuid,uuid,uuid),hisaab.import_state(uuid);
      DROP FUNCTION hisaab.import_evidence_hash(uuid,uuid);
      NOTIFY pgrst,'reload schema';
    """)
