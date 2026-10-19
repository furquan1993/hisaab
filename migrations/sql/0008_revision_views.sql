CREATE VIEW hisaab.all_extracted_entries WITH (security_invoker=true) AS
SELECT e.id,e.import_id,s.id AS statement_id,c.label AS card_label,c.bank,
 s.statement_date,e.transaction_date,e.description,e.amount::text AS amount,e.direction,e.currency,e.entry_type,e.sequence,
 (s.active_import_id IS NOT DISTINCT FROM i.id) AS is_selected,
 (s.active_import_id IS DISTINCT FROM i.id OR e.transaction_date IS NULL OR s.statement_date IS NULL OR
  jsonb_array_length(e.issues::jsonb)>0 OR EXISTS(SELECT 1 FROM jsonb_array_elements(i.issues::jsonb) x
    WHERE x->>'code' NOT IN ('competing_statement_file','ambiguous_statement_match','statement_match_unresolved'))) AS needs_review,
 e.issues::jsonb AS entry_issues,i.issues::jsonb AS import_issues,i.review_status
FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id;
CREATE OR REPLACE VIEW hisaab.extracted_entries WITH (security_invoker=true) AS
 SELECT * FROM hisaab.all_extracted_entries e WHERE hisaab.import_state(e.import_id) IN ('selected','candidate');

CREATE VIEW hisaab_api.revision_entries WITH (security_invoker=true) AS
SELECT e.*,hisaab.logical_entry_id(e.id) AS logical_entry_id,coalesce(d.version,0) AS decision_version,
 d.category_id,c.name AS category_name,d.account_id,a.name AS account_name,
 coalesce(d.overrides::jsonb,'{}'::jsonb) AS overrides,coalesce(d.acknowledged::jsonb,'[]'::jsonb) AS acknowledged,
 d.source_fingerprint,d.updated_at AS decision_updated_at
FROM hisaab.all_extracted_entries e
LEFT JOIN hisaab.entry_decisions d ON d.entry_id=hisaab.logical_entry_id(e.id) AND d.owner_id=hisaab.current_owner_id()
LEFT JOIN hisaab.categories c ON c.id=d.category_id AND c.owner_id=d.owner_id
LEFT JOIN hisaab.accounts a ON a.id=d.account_id AND a.owner_id=d.owner_id;

CREATE VIEW hisaab_api.sources WITH (security_invoker=true) AS
SELECT i.id,i.statement_id,c.label AS card_label,c.bank,s.statement_date,i.source_import_id,
 i.source_filename,i.file_sha256,i.parsed_statement_date,i.page_count,i.parser_version,i.extractor_version,
 i.issues::jsonb AS issues,hisaab.import_state(i.id) AS state,i.created_at,
 (SELECT count(*) FROM hisaab.entries e WHERE e.import_id=i.id AND e.owner_id=i.owner_id) AS entry_count
FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id;

CREATE VIEW hisaab_api.revisions WITH (security_invoker=true) AS
SELECT r.id,r.statement_id,r.base_import_id,r.candidate_import_id,r.version,r.status,r.plan::jsonb AS plan,
 r.reviewed_mapping::jsonb AS reviewed_mapping,r.reason,r.created_at,r.decided_at,
 (r.status='pending' AND s.active_import_id IS DISTINCT FROM r.base_import_id) AS is_stale
FROM hisaab.parser_revisions r JOIN hisaab.statements s ON s.id=r.statement_id AND s.owner_id=r.owner_id;

CREATE OR REPLACE VIEW hisaab_api.entry_evidence WITH (security_invoker=true) AS
SELECT e.id,e.import_id,e.raw_date,e.raw_time,e.raw_amount,e.source_page,e.source_bbox,e.source_raw_text,e.section,
 i.source_filename,i.file_sha256,coalesce(p.pdf_deleted_at,i.pdf_deleted_at) AS pdf_deleted_at,
 i.page_count,i.parser_version,i.extractor_version
FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
LEFT JOIN hisaab.imports p ON p.id=i.source_import_id AND p.owner_id=i.owner_id;

CREATE OR REPLACE FUNCTION hisaab_api.original_pdf(p_import_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE source hisaab.imports; payload hisaab.imports;
BEGIN
 SELECT * INTO source FROM hisaab.imports WHERE id=p_import_id AND owner_id=hisaab.current_owner_id();
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF source.source_import_id IS NULL THEN payload:=source;
 ELSE
   SELECT * INTO payload FROM hisaab.imports WHERE id=source.source_import_id AND owner_id=source.owner_id;
   IF NOT FOUND OR payload.source_import_id IS NOT NULL OR
      (payload.card_id,payload.statement_id,payload.file_sha256,payload.file_size_bytes) IS DISTINCT FROM
      (source.card_id,source.statement_id,source.file_sha256,source.file_size_bytes) THEN
     RAISE EXCEPTION 'Original source integrity check failed' USING ERRCODE='XX001';
   END IF;
 END IF;
 IF payload.pdf_bytes IS NULL THEN RETURN NULL; END IF;
 IF length(payload.pdf_bytes)<>payload.file_size_bytes OR encode(sha256(payload.pdf_bytes),'hex')<>payload.file_sha256 THEN
   RAISE EXCEPTION 'Original integrity check failed' USING ERRCODE='XX001';
 END IF;
 RETURN jsonb_build_object('sha256',payload.file_sha256,'content_base64',encode(payload.pdf_bytes,'base64'));
END $$;

CREATE FUNCTION hisaab_api.prepare_revision(p_candidate_import_id uuid) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT hisaab.prepare_revision_for_owner(hisaab.current_owner_id(),p_candidate_import_id)
$$;
CREATE FUNCTION hisaab_api.accept_revision(p_revision_id uuid,p_mapping jsonb,p_removed jsonb,p_reason text,p_ack_metadata boolean DEFAULT false) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT hisaab.accept_revision_for_owner(hisaab.current_owner_id(),p_revision_id,p_mapping,p_removed,p_reason,p_ack_metadata)
$$;
CREATE FUNCTION hisaab_api.reject_revision(p_revision_id uuid,p_reason text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT hisaab.reject_revision_for_owner(hisaab.current_owner_id(),p_revision_id,p_reason)
$$;
