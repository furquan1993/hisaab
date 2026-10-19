-- Invoker views preserve the existing owner RLS chain.
-- https://www.postgresql.org/docs/17/sql-createview.html
CREATE VIEW hisaab_api.spending_groups WITH (security_invoker=true) AS
 SELECT id,name,is_archived,version FROM hisaab.spending_groups;
CREATE VIEW hisaab_api.spending_entries WITH (security_invoker=true) AS
 SELECT e.*,a.group_id,g.name AS group_name,coalesce(a.version,0) AS group_version
 FROM hisaab_api.entries e
 LEFT JOIN hisaab.spending_assignments a ON a.entry_id=e.logical_entry_id AND a.owner_id=hisaab.current_owner_id()
 LEFT JOIN hisaab.spending_groups g ON g.id=a.group_id AND g.owner_id=a.owner_id
 WHERE e.is_selected;

CREATE FUNCTION hisaab_api.save_spending_group(
 p_name text,p_id uuid DEFAULT NULL,p_expected_version integer DEFAULT 0,
 p_archived boolean DEFAULT false,p_expected_owner uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner_ uuid:=hisaab.current_owner_id(); saved hisaab.spending_groups;
BEGIN
 IF owner_ IS NULL OR owner_ IS DISTINCT FROM p_expected_owner THEN
  RAISE SQLSTATE '42501' USING MESSAGE='Reload your signed-in workspace';
 END IF;
 IF p_name IS NULL OR length(btrim(p_name)) NOT BETWEEN 1 AND 120 OR p_name ~ '[[:cntrl:]]'
 OR p_archived IS NULL OR p_expected_version IS NULL OR p_expected_version<0 THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Use a group name of 1 to 120 characters';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(owner_::text||':'||'spending_groups',0));
 IF p_id IS NOT NULL THEN
  SELECT * INTO saved FROM hisaab.spending_groups WHERE owner_id=owner_ AND id=p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Group is unavailable'; END IF;
  IF saved.version<>p_expected_version THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Group changed; reload before saving'; END IF;
 ELSIF p_expected_version<>0 THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Reload groups before saving';
 END IF;
 IF EXISTS(SELECT 1 FROM hisaab.spending_groups WHERE owner_id=owner_ AND lower(name)=lower(btrim(p_name)) AND id IS DISTINCT FROM p_id) THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='This group name already exists';
 END IF;
 IF p_id IS NULL THEN
  INSERT INTO hisaab.spending_groups(id,owner_id,name,is_archived)
  VALUES(gen_random_uuid(),owner_,btrim(p_name),p_archived) RETURNING * INTO saved;
 ELSE
  UPDATE hisaab.spending_groups SET name=btrim(p_name),is_archived=p_archived,version=version+1
  WHERE id=p_id AND owner_id=owner_ RETURNING * INTO saved;
 END IF;
 RETURN to_jsonb(saved)-'owner_id'-'created_at';
END $$;

CREATE FUNCTION hisaab_api.assign_spending_group(p_group_id uuid,p_entries jsonb,p_expected_owner uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner_ uuid:=hisaab.current_owner_id(); item jsonb; source hisaab.entries;
 previous hisaab.spending_assignments; saved hisaab.spending_assignments;
 root_ uuid; roots_ uuid[]:='{}'; result_ jsonb:='[]'; active_ uuid;
 expected_ integer; decision_ hisaab.entry_decisions;
BEGIN
 IF owner_ IS NULL OR owner_ IS DISTINCT FROM p_expected_owner THEN
  RAISE SQLSTATE '42501' USING MESSAGE='Reload your signed-in workspace';
 END IF;
 IF p_entries IS NULL OR jsonb_typeof(p_entries)<>'array' THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Choose 1 to 50 entries';
 END IF;
 IF jsonb_array_length(p_entries) NOT BETWEEN 1 AND 50 THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Choose 1 to 50 entries';
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_entries) LOOP
  IF jsonb_typeof(item)<>'object' OR NOT (item ?& ARRAY['id','version']) OR
   EXISTS(SELECT 1 FROM jsonb_object_keys(item) k WHERE k NOT IN ('id','version')) OR
   jsonb_typeof(item->'id') IS DISTINCT FROM 'string' OR jsonb_typeof(item->'version') IS DISTINCT FROM 'number' OR
   (item->>'version') !~ '^[0-9]+$' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid entry references';
  END IF;
 END LOOP;
 -- Share stable statement locking with revision/review/contribution operations.
 PERFORM s.id FROM hisaab.statements s WHERE s.owner_id=owner_ AND EXISTS(
  SELECT 1 FROM hisaab.imports i JOIN hisaab.entries e ON e.import_id=i.id AND e.owner_id=i.owner_id
  WHERE i.owner_id=owner_ AND i.statement_id=s.id AND e.id IN (SELECT (value->>'id')::uuid FROM jsonb_array_elements(p_entries))
 ) ORDER BY s.id FOR UPDATE;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(owner_::text||':'||'spending_groups',0));
 IF p_group_id IS NOT NULL THEN
  PERFORM 1 FROM hisaab.spending_groups WHERE id=p_group_id AND owner_id=owner_ AND NOT is_archived FOR SHARE;
  IF NOT FOUND THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose an available group'; END IF;
 END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(p_entries) LOOP
  SELECT e.* INTO source FROM hisaab.entries e
   JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
   JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
   WHERE e.id=(item->>'id')::uuid AND e.owner_id=owner_;
  IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Entry is unavailable'; END IF;
  SELECT s.active_import_id INTO active_ FROM hisaab.statements s
   JOIN hisaab.imports i ON i.statement_id=s.id AND i.owner_id=s.owner_id WHERE i.id=source.import_id AND i.owner_id=owner_;
  IF active_ IS DISTINCT FROM source.import_id THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; reload before assigning'; END IF;
  root_:=hisaab.logical_entry_id(source.id);
  IF root_=ANY(roots_) THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose each entry once'; END IF;
  roots_:=array_append(roots_,root_);
  SELECT * INTO decision_ FROM hisaab.entry_decisions WHERE owner_id=owner_ AND entry_id=root_;
  IF hisaab.effective_values(source,decision_)->>'entry_type'='payment' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Card repayments are excluded from spending groups';
  END IF;
  SELECT * INTO previous FROM hisaab.spending_assignments WHERE owner_id=owner_ AND entry_id=root_ FOR UPDATE;
  expected_:=(item->>'version')::integer;
  IF coalesce(previous.version,0)<>expected_ THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Group assignment changed; reload before saving'; END IF;
  IF previous.group_id IS NOT DISTINCT FROM p_group_id THEN
   result_:=result_||jsonb_build_array(jsonb_build_object('entry_id',root_,'group_id',p_group_id,'version',expected_));
   CONTINUE;
  END IF;
  INSERT INTO hisaab.spending_assignments(id,owner_id,entry_id,group_id,version)
  VALUES(gen_random_uuid(),owner_,root_,p_group_id,expected_+1)
  ON CONFLICT(owner_id,entry_id) DO UPDATE SET group_id=excluded.group_id,version=excluded.version RETURNING * INTO saved;
  INSERT INTO hisaab.spending_events(id,owner_id,entry_id,version,actor_auth_user_id,"before","after")
  VALUES(gen_random_uuid(),owner_,root_,saved.version,
   (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid,
   coalesce(to_jsonb(previous),'{}'::jsonb),to_jsonb(saved));
  result_:=result_||jsonb_build_array(jsonb_build_object('entry_id',root_,'group_id',p_group_id,'version',saved.version));
 END LOOP;
 RETURN result_;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE SQLSTATE 'PT422' USING MESSAGE='Use valid entry identifiers and versions';
END $$;

REVOKE ALL ON hisaab.spending_groups,hisaab.spending_assignments,hisaab.spending_events,
 hisaab_api.spending_groups,hisaab_api.spending_entries FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab_api.save_spending_group(text,uuid,integer,boolean,uuid),
 hisaab_api.assign_spending_group(uuid,jsonb,uuid) FROM PUBLIC;
DO $$ DECLARE role_ text; BEGIN
 FOREACH role_ IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_) THEN
   EXECUTE format('REVOKE ALL ON hisaab.spending_groups,hisaab.spending_assignments,hisaab.spending_events,hisaab_api.spending_groups,hisaab_api.spending_entries FROM %I',role_);
   EXECUTE format('REVOKE ALL ON FUNCTION hisaab_api.save_spending_group(text,uuid,integer,boolean,uuid),hisaab_api.assign_spending_group(uuid,jsonb,uuid) FROM %I',role_);
  END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT SELECT ON hisaab.spending_groups,hisaab.spending_assignments,hisaab.spending_events,hisaab_api.spending_groups,hisaab_api.spending_entries TO authenticated;
  GRANT EXECUTE ON FUNCTION hisaab_api.save_spending_group(text,uuid,integer,boolean,uuid),hisaab_api.assign_spending_group(uuid,jsonb,uuid) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
