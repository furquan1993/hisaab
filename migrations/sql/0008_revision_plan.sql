CREATE FUNCTION hisaab.import_evidence_hash(p_owner uuid,p_import uuid) RETURNS text
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(jsonb_build_array(
   i.file_sha256,i.file_size_bytes,i.source_filename,i.page_count,i.source_import_id,
   i.card_id,i.statement_id,i.parsed_statement_date,i.parser_version,
   i.extractor_version,i.schema_version,i.review_status,i.issues::jsonb,
   (SELECT jsonb_agg(jsonb_build_array(e.id,e.sequence,hisaab.entry_fingerprint(e)) ORDER BY e.sequence)
    FROM hisaab.entries e WHERE e.owner_id=p_owner AND e.import_id=i.id)
 )::text,'UTF8')),'hex') FROM hisaab.imports i WHERE i.id=p_import AND i.owner_id=p_owner
$$;

CREATE FUNCTION hisaab.revision_plan(p_owner uuid,p_base uuid,p_candidate uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 WITH old_rows AS (
   SELECT e.id,e.sequence,hisaab.entry_fingerprint(e) AS signature FROM hisaab.entries e
   WHERE e.owner_id=p_owner AND e.import_id=p_base
 ), new_rows AS (
   SELECT e.id,e.sequence,hisaab.entry_fingerprint(e) AS signature FROM hisaab.entries e
   WHERE e.owner_id=p_owner AND e.import_id=p_candidate
 ), matches AS (
   SELECT n.id AS new_id,b.id AS old_id,n.sequence
   FROM old_rows b JOIN new_rows n ON n.signature=b.signature AND n.sequence=b.sequence
   WHERE (SELECT count(*) FROM old_rows x WHERE x.signature=b.signature)=1
     AND (SELECT count(*) FROM new_rows x WHERE x.signature=n.signature)=1
 ) SELECT jsonb_build_object(
   'matches',coalesce((SELECT jsonb_agg(jsonb_build_object('new_entry_id',new_id,'previous_entry_id',old_id) ORDER BY sequence) FROM matches),'[]'::jsonb),
   'unmatched_new',coalesce((SELECT jsonb_agg(n.id ORDER BY n.sequence) FROM new_rows n WHERE NOT EXISTS(SELECT 1 FROM matches m WHERE m.new_id=n.id)),'[]'::jsonb),
   'unmatched_old',coalesce((SELECT jsonb_agg(b.id ORDER BY b.sequence) FROM old_rows b WHERE NOT EXISTS(SELECT 1 FROM matches m WHERE m.old_id=b.id)),'[]'::jsonb),
   'base_hash',hisaab.import_evidence_hash(p_owner,p_base),
   'candidate_hash',hisaab.import_evidence_hash(p_owner,p_candidate),
   'metadata_changed',coalesce((SELECT b.parsed_statement_date IS DISTINCT FROM n.parsed_statement_date
      FROM hisaab.imports b JOIN hisaab.imports n ON n.owner_id=b.owner_id
      WHERE b.id=p_base AND n.id=p_candidate AND b.owner_id=p_owner),false)
 )
$$;

CREATE FUNCTION hisaab.prepare_revision_for_owner(p_owner uuid,p_candidate uuid) RETURNS jsonb
LANGUAGE plpgsql SET search_path='' AS $$
DECLARE candidate hisaab.imports; bill hisaab.statements; saved hisaab.parser_revisions; next_version integer;
BEGIN
 IF p_owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 SELECT i.* INTO candidate FROM hisaab.imports i WHERE i.owner_id=p_owner AND i.id=p_candidate;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Candidate is unavailable'; END IF;
 SELECT * INTO bill FROM hisaab.statements WHERE owner_id=p_owner AND id=candidate.statement_id FOR UPDATE;
 IF bill.active_import_id=p_candidate OR EXISTS(SELECT 1 FROM hisaab.parser_revisions r
      WHERE r.owner_id=p_owner AND r.status='accepted' AND (r.base_import_id=p_candidate OR r.candidate_import_id=p_candidate)) THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Use a fresh parser revision rather than rebinding published evidence';
 END IF;
 SELECT * INTO saved FROM hisaab.parser_revisions r WHERE r.owner_id=p_owner AND r.candidate_import_id=p_candidate
   AND r.base_import_id IS NOT DISTINCT FROM bill.active_import_id AND r.status='pending' ORDER BY r.version DESC LIMIT 1;
 IF FOUND THEN RETURN to_jsonb(saved)-'owner_id'; END IF;
 SELECT coalesce(max(version),0)+1 INTO next_version FROM hisaab.parser_revisions WHERE owner_id=p_owner AND candidate_import_id=p_candidate;
 INSERT INTO hisaab.parser_revisions(id,owner_id,statement_id,base_import_id,candidate_import_id,version,plan)
 VALUES(gen_random_uuid(),p_owner,bill.id,bill.active_import_id,p_candidate,next_version,
   hisaab.revision_plan(p_owner,bill.active_import_id,p_candidate)) RETURNING * INTO saved;
 RETURN to_jsonb(saved)-'owner_id';
END $$;

CREATE OR REPLACE FUNCTION hisaab.logical_entry_id(p_id uuid) RETURNS uuid
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT coalesce((SELECT logical_entry_id FROM hisaab.entry_links WHERE entry_id=p_id),p_id)
$$;

CREATE FUNCTION hisaab.import_state(p_id uuid) RETURNS text
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT CASE WHEN s.active_import_id=i.id THEN 'selected'
 WHEN EXISTS(SELECT 1 FROM hisaab.parser_revisions r WHERE r.owner_id=i.owner_id AND r.status='accepted' AND (r.base_import_id=i.id OR r.candidate_import_id=i.id)) THEN 'superseded'
 WHEN (SELECT r.status FROM hisaab.parser_revisions r WHERE r.owner_id=i.owner_id AND r.candidate_import_id=i.id ORDER BY r.version DESC LIMIT 1)='rejected' THEN 'rejected'
 ELSE 'candidate' END
 FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id WHERE i.id=p_id
$$;
