CREATE FUNCTION hisaab.accept_revision_for_owner(
 p_owner uuid,p_revision uuid,p_mapping jsonb,p_removed jsonb,p_reason text,p_ack_metadata boolean
) RETURNS jsonb LANGUAGE plpgsql SET search_path='' AS $$
DECLARE draft hisaab.parser_revisions; bill hisaab.statements; item jsonb; complete_map jsonb;
        old_id uuid; new_id uuid; logical_id uuid; wanted_removed jsonb; supplied_removed jsonb;
BEGIN
 IF p_owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 SELECT * INTO draft FROM hisaab.parser_revisions WHERE id=p_revision AND owner_id=p_owner;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Revision is unavailable'; END IF;
 SELECT * INTO bill FROM hisaab.statements WHERE id=draft.statement_id AND owner_id=p_owner FOR UPDATE;
 SELECT * INTO draft FROM hisaab.parser_revisions WHERE id=p_revision AND owner_id=p_owner FOR UPDATE;
 IF draft.status='accepted' AND bill.active_import_id=draft.candidate_import_id THEN RETURN to_jsonb(draft)-'owner_id'; END IF;
 IF draft.status<>'pending' OR bill.active_import_id IS DISTINCT FROM draft.base_import_id THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; prepare and review a fresh comparison';
 END IF;
 IF p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 OR
    p_mapping IS NULL OR jsonb_typeof(p_mapping)<>'array' OR p_removed IS NULL OR jsonb_typeof(p_removed)<>'array' OR
    p_ack_metadata IS NULL THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Review mappings and provide a reason'; END IF;
 IF hisaab.revision_plan(p_owner,draft.base_import_id,draft.candidate_import_id) IS DISTINCT FROM draft.plan::jsonb THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Evidence changed; prepare a fresh comparison';
 END IF;
 IF (draft.plan::jsonb->>'metadata_changed')::boolean AND NOT p_ack_metadata THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Explicitly acknowledge the statement metadata change';
 END IF;
 IF jsonb_array_length(p_mapping)<>jsonb_array_length(draft.plan::jsonb->'unmatched_new') OR
    (SELECT count(DISTINCT x->>'new_entry_id') FROM jsonb_array_elements(p_mapping) x)<>jsonb_array_length(p_mapping) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Every uncertain new row needs exactly one explicit identity decision';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_mapping) LOOP
   IF jsonb_typeof(item)<>'object' OR NOT(item ? 'new_entry_id') OR NOT(item ? 'previous_entry_id') OR
      jsonb_typeof(item->'new_entry_id')<>'string' OR jsonb_typeof(item->'previous_entry_id') NOT IN ('string','null') OR
      EXISTS(SELECT 1 FROM jsonb_object_keys(item) k WHERE k NOT IN ('new_entry_id','previous_entry_id')) OR
      NOT((draft.plan::jsonb->'unmatched_new') ? (item->>'new_entry_id')) THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid identity mapping';
   END IF;
   new_id:=(item->>'new_entry_id')::uuid;
   old_id:=(item->>'previous_entry_id')::uuid;
   IF old_id IS NOT NULL AND NOT((draft.plan::jsonb->'unmatched_old') ? old_id::text) THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Choose a row from the published source or explicitly declare a new entry';
   END IF;
 END LOOP;
 complete_map:=(draft.plan::jsonb->'matches')||p_mapping;
 IF (SELECT count(*) FROM jsonb_array_elements(complete_map) x WHERE x->>'previous_entry_id' IS NOT NULL)<>
    (SELECT count(DISTINCT x->>'previous_entry_id') FROM jsonb_array_elements(complete_map) x WHERE x->>'previous_entry_id' IS NOT NULL) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='An existing identity cannot be assigned to multiple new rows';
 END IF;
 SELECT coalesce(jsonb_agg(e.id::text ORDER BY e.id::text),'[]'::jsonb) INTO wanted_removed FROM hisaab.entries e
 WHERE e.owner_id=p_owner AND e.import_id=draft.base_import_id AND NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(complete_map) x WHERE x->>'previous_entry_id'=e.id::text);
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_removed) x WHERE jsonb_typeof(x)<>'string') OR
    (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_removed))<>jsonb_array_length(p_removed) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid removed-row acknowledgement';
 END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY value),'[]'::jsonb) INTO supplied_removed FROM jsonb_array_elements_text(p_removed);
 IF supplied_removed<>wanted_removed THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Explicitly acknowledge every removed published row; its decisions remain in history';
 END IF;
 IF EXISTS(SELECT 1 FROM hisaab.entry_links WHERE owner_id=p_owner AND import_id=draft.candidate_import_id) THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Previously published evidence cannot be rebound';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(complete_map) LOOP
   new_id:=(item->>'new_entry_id')::uuid;old_id:=(item->>'previous_entry_id')::uuid;
   IF old_id IS NOT NULL THEN
     logical_id:=hisaab.logical_entry_id(old_id);
     INSERT INTO hisaab.entry_links(id,owner_id,import_id,entry_id,logical_entry_id,revision_id)
       VALUES(gen_random_uuid(),p_owner,draft.candidate_import_id,new_id,logical_id,draft.id);
   END IF;
 END LOOP;
 UPDATE hisaab.statements SET active_import_id=draft.candidate_import_id WHERE id=bill.id AND owner_id=p_owner;
 UPDATE hisaab.parser_revisions SET status='accepted',reviewed_mapping=complete_map,reason=btrim(p_reason),
   decided_at=CURRENT_TIMESTAMP,actor_auth_user_id=(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid
   WHERE id=draft.id AND owner_id=p_owner RETURNING * INTO draft;
 RETURN to_jsonb(draft)-'owner_id';
EXCEPTION WHEN invalid_text_representation THEN
 RAISE SQLSTATE 'PT422' USING MESSAGE='Use valid entry identifiers';
END $$;

CREATE FUNCTION hisaab.reject_revision_for_owner(p_owner uuid,p_revision uuid,p_reason text) RETURNS jsonb
LANGUAGE plpgsql SET search_path='' AS $$
DECLARE draft hisaab.parser_revisions;
BEGIN
 IF p_owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 SELECT * INTO draft FROM hisaab.parser_revisions WHERE id=p_revision AND owner_id=p_owner;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Revision is unavailable'; END IF;
 PERFORM 1 FROM hisaab.statements WHERE id=draft.statement_id AND owner_id=p_owner FOR UPDATE;
 SELECT * INTO draft FROM hisaab.parser_revisions WHERE id=p_revision AND owner_id=p_owner FOR UPDATE;
 IF draft.status='rejected' THEN RETURN to_jsonb(draft)-'owner_id'; END IF;
 IF draft.status<>'pending' THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Revision has already been decided'; END IF;
 IF p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Provide a reason for rejecting this source';
 END IF;
 UPDATE hisaab.parser_revisions SET status='rejected',reason=btrim(p_reason),decided_at=CURRENT_TIMESTAMP,
   actor_auth_user_id=(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid
   WHERE id=draft.id AND owner_id=p_owner RETURNING * INTO draft;
 RETURN to_jsonb(draft)-'owner_id';
END $$;
