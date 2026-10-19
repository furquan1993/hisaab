CREATE FUNCTION hisaab_api.review_import(
 p_import_id uuid,p_expected_version integer,p_acknowledged jsonb,p_reason text,p_statement_date text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); source record; previous hisaab.import_reviews; saved hisaab.import_reviews;
 root uuid; key_ text; date_ date;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_version IS NULL OR p_expected_version<0 OR p_acknowledged IS NULL OR jsonb_typeof(p_acknowledged)<>'array' OR
    p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Provide valid coverage acknowledgements and a reason';
 END IF;
 SELECT i.id,i.owner_id,i.statement_id,i.source_import_id,i.file_sha256,i.page_count,i.parsed_statement_date,i.issues INTO source
 FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
 WHERE i.id=p_import_id AND i.owner_id=owner FOR UPDATE OF s;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Import is unavailable'; END IF;
 IF NOT EXISTS(SELECT 1 FROM hisaab.statements WHERE id=source.statement_id AND owner_id=owner AND active_import_id=source.id) THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; reload before reviewing coverage';
 END IF;
 root:=coalesce(source.source_import_id,source.id);
 SELECT * INTO previous FROM hisaab.import_reviews WHERE owner_id=owner AND import_id=root ORDER BY version DESC LIMIT 1;
 IF coalesce(previous.version,0)<>p_expected_version THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Statement review changed; reload before saving'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_acknowledged) x WHERE jsonb_typeof(x)<>'string') OR
    (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_acknowledged))<>jsonb_array_length(p_acknowledged) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid coverage acknowledgements';
 END IF;
 FOR key_ IN SELECT jsonb_array_elements_text(p_acknowledged) LOOP
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(source.issues::jsonb) x WHERE hisaab.issue_key(x)=key_ AND NOT hisaab.critical_issue(x->>'code')
    AND x->>'code' NOT IN ('competing_statement_file','ambiguous_statement_match','statement_match_unresolved')) THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Acknowledge coverage warnings only; correct dates or review source selection separately';
   END IF;
 END LOOP;
 IF p_statement_date IS NOT NULL THEN
   IF p_statement_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Use a valid ISO statement date'; END IF;
   date_:=p_statement_date::date;
 END IF;
 INSERT INTO hisaab.import_reviews(id,owner_id,import_id,reviewed_import_id,version,source_fingerprint,acknowledged,statement_date_override,reason,actor_auth_user_id)
 VALUES(gen_random_uuid(),owner,root,source.id,p_expected_version+1,
   hisaab.coverage_fingerprint(source.file_sha256,source.page_count,source.parsed_statement_date,source.issues::jsonb),
   p_acknowledged,date_,btrim(p_reason),(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid)
 RETURNING * INTO saved;
 RETURN to_jsonb(saved)-'owner_id';
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow THEN
 RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid statement review value';
END $$;
