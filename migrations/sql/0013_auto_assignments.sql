-- Exact normalized merchant matches; retain short numeric identifiers (e.g. 7-Eleven).
CREATE FUNCTION hisaab.merchant_key(p_description text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path='' AS $$
 SELECT btrim(regexp_replace(regexp_replace(lower(p_description),'[0-9]{6,}',' ','g'),'[^a-z0-9]+',' ','g'))
$$;
ALTER TABLE hisaab.assignment_examples ENABLE ROW LEVEL SECURITY;
CREATE POLICY browser_read ON hisaab.assignment_examples FOR SELECT USING(owner_id=(SELECT hisaab.current_owner_id()));

-- Existing explicit decisions are protected, including intentionally empty labels.
INSERT INTO hisaab.assignment_examples(id,owner_id,source_key,merchant_key,direction,kind,is_manual,entry_id,account_id,category_id,observed_at)
 SELECT gen_random_uuid(),d.owner_id,'manual:'||d.entry_id,hisaab.merchant_key(hisaab.effective_values(e,d)->>'description'),coalesce(hisaab.effective_values(e,d)->>'direction','unknown'),k.kind,true,d.entry_id,
 CASE WHEN k.kind='account' THEN d.account_id END,CASE WHEN k.kind='category' THEN d.category_id END,d.updated_at
 FROM hisaab.entry_decisions d JOIN hisaab.entries e ON e.id=d.entry_id AND e.owner_id=d.owner_id
 CROSS JOIN (VALUES ('account'),('category')) k(kind);

ALTER FUNCTION hisaab_api.save_entry_decision(uuid,integer,jsonb) RENAME TO save_entry_decision_without_learning;
ALTER FUNCTION hisaab_api.save_entry_decision_without_learning(uuid,integer,jsonb) SET SCHEMA hisaab;
CREATE FUNCTION hisaab_api.save_entry_decision(p_entry_id uuid,p_expected_version integer,p_patch jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved jsonb; source hisaab.entries; effective jsonb; kind_ text; root uuid;
BEGIN
 saved:=hisaab.save_entry_decision_without_learning(p_entry_id,p_expected_version,p_patch);
 SELECT * INTO source FROM hisaab.entries WHERE id=p_entry_id AND owner_id=hisaab.current_owner_id();
 root:=hisaab.logical_entry_id(p_entry_id);
 SELECT hisaab.effective_values(source,d) INTO effective FROM hisaab.entry_decisions d
 WHERE d.owner_id=source.owner_id AND d.entry_id=root;
 FOREACH kind_ IN ARRAY ARRAY['account','category'] LOOP
   IF p_patch ? (kind_||'_id') THEN
    INSERT INTO hisaab.assignment_examples(id,owner_id,source_key,merchant_key,direction,kind,is_manual,entry_id,account_id,category_id,observed_at)
    VALUES(gen_random_uuid(),source.owner_id,'manual:'||root,hisaab.merchant_key(effective->>'description'),coalesce(effective->>'direction','unknown'),kind_,true,root,
      CASE WHEN kind_='account' THEN (saved->>'account_id')::uuid END,
      CASE WHEN kind_='category' THEN (saved->>'category_id')::uuid END,clock_timestamp())
    ON CONFLICT(owner_id,source_key,kind) DO UPDATE SET merchant_key=excluded.merchant_key,direction=excluded.direction,
     account_id=excluded.account_id,category_id=excluded.category_id,observed_at=excluded.observed_at;
   END IF;
 END LOOP;
 RETURN saved;
END $$;

CREATE FUNCTION hisaab.assignment_prediction(p_owner uuid,p_key text,p_direction text,p_kind text)
RETURNS uuid LANGUAGE plpgsql SET search_path='' AS $$
DECLARE chosen uuid; n integer; total integer;
BEGIN
 -- The most recent explicit correction wins, even an explicit removal.
 SELECT CASE WHEN p_kind='account' THEN x.account_id ELSE x.category_id END INTO chosen
 FROM hisaab.assignment_examples x WHERE x.owner_id=p_owner AND x.merchant_key=p_key
 AND x.direction=p_direction AND x.kind=p_kind AND x.is_manual ORDER BY x.observed_at DESC,x.id DESC LIMIT 1;
 IF FOUND THEN RETURN chosen; END IF;
 SELECT count(*) INTO total FROM hisaab.assignment_examples x WHERE x.owner_id=p_owner AND x.merchant_key=p_key
 AND x.direction=p_direction AND x.kind=p_kind AND NOT x.is_manual;
 SELECT CASE WHEN p_kind='account' THEN x.account_id ELSE x.category_id END,count(*) INTO chosen,n
 FROM hisaab.assignment_examples x WHERE x.owner_id=p_owner AND x.merchant_key=p_key
 AND x.direction=p_direction AND x.kind=p_kind AND NOT x.is_manual
 GROUP BY 1 ORDER BY count(*) DESC LIMIT 1;
 IF n>=2 AND n::numeric / nullif(total,0)>=0.9 THEN RETURN chosen; END IF;
 RETURN NULL;
END $$;

CREATE FUNCTION hisaab.apply_entry_assignments(p_owner uuid,p_entry uuid) RETURNS boolean
LANGUAGE plpgsql SET search_path='' AS $$
DECLARE source hisaab.entries; previous hisaab.entry_decisions; saved hisaab.entry_decisions;
 root uuid; account uuid; category uuid; key_ text; effective jsonb; category_name_ text;
BEGIN
 -- Share the statement lock used by review, assignments, source replacement and settlement.
 SELECT e.* INTO source FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
 JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
 WHERE e.id=p_entry AND e.owner_id=p_owner AND s.active_import_id=i.id FOR UPDATE OF s;
 IF NOT FOUND THEN RETURN false; END IF;
 root:=hisaab.logical_entry_id(source.id);
 SELECT * INTO previous FROM hisaab.entry_decisions WHERE owner_id=p_owner AND entry_id=root FOR UPDATE;
 effective:=hisaab.effective_values(source,previous);
 IF effective->>'direction' NOT IN ('debit','credit') OR effective->>'direction' IS NULL
 OR effective->>'entry_type' IN ('payment','unknown') THEN RETURN false; END IF;
 key_:=hisaab.merchant_key(effective->>'description');
 IF length(key_)<3 THEN RETURN false; END IF;
 -- Acquire this before any category row locks, including across a batch.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_owner::text||':'||'categories',0));
 account:=previous.account_id;category:=previous.category_id;
 IF account IS NULL AND NOT EXISTS(SELECT 1 FROM hisaab.assignment_examples WHERE owner_id=p_owner AND entry_id=root AND kind='account' AND is_manual) THEN
  account:=hisaab.assignment_prediction(p_owner,key_,effective->>'direction','account');
  SELECT id INTO account FROM hisaab.accounts WHERE id=account AND owner_id=p_owner AND NOT is_archived FOR SHARE;
 END IF;
 IF category IS NULL AND NOT EXISTS(SELECT 1 FROM hisaab.assignment_examples WHERE owner_id=p_owner AND entry_id=root AND kind='category' AND is_manual) THEN
  category:=hisaab.assignment_prediction(p_owner,key_,effective->>'direction','category');
  -- A manual removal or archived learned category suppresses the starter rules as well.
  IF category IS NULL AND NOT EXISTS(SELECT 1 FROM hisaab.assignment_examples WHERE owner_id=p_owner AND merchant_key=key_ AND direction=effective->>'direction' AND kind='category') THEN
   category_name_:=CASE
    WHEN effective->>'entry_type' IN ('fee','tax') THEN 'Fees & Taxes'
    WHEN effective->>'entry_type'='interest' THEN 'Interest'
    WHEN effective->>'entry_type'='cashback' THEN 'Cashback'
    WHEN key_ ~ '(^| )(instamart|bigbasket|blinkit|zepto)( |$)' THEN 'Groceries'
    WHEN key_ ~ '(^| )(swiggy|zomato)( |$)' THEN 'Dining'
    WHEN key_ ~ '(^| )(irctc|uber|ola)( |$)' THEN 'Transport'
    WHEN key_ ~ '(^| )(petrol|petroleum|fuel)( |$)' THEN 'Fuel'
    WHEN key_ ~ '(^| )(netflix|spotify)( |$)' THEN 'Subscriptions'
    ELSE NULL END;
   IF category_name_ IS NOT NULL THEN
    INSERT INTO hisaab.categories(id,owner_id,name) SELECT gen_random_uuid(),p_owner,category_name_
     WHERE NOT EXISTS(SELECT 1 FROM hisaab.categories WHERE owner_id=p_owner AND lower(name)=lower(category_name_))
     ON CONFLICT(owner_id,name) DO NOTHING;
    SELECT id INTO category FROM hisaab.categories WHERE owner_id=p_owner AND lower(name)=lower(category_name_) AND NOT is_archived ORDER BY id LIMIT 1;
   END IF;
  END IF;
  SELECT id INTO category FROM hisaab.categories WHERE id=category AND owner_id=p_owner AND NOT is_archived FOR SHARE;
 END IF;
 IF account IS NOT DISTINCT FROM previous.account_id AND category IS NOT DISTINCT FROM previous.category_id THEN RETURN false; END IF;
 INSERT INTO hisaab.entry_decisions(id,owner_id,entry_id,account_id,category_id,version,reason)
 VALUES(gen_random_uuid(),p_owner,root,account,category,coalesce(previous.version,0)+1,'Automatically assigned from history, corrections or starter category rules')
 ON CONFLICT(owner_id,entry_id) DO UPDATE SET account_id=excluded.account_id,category_id=excluded.category_id,
 version=excluded.version,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP RETURNING * INTO saved;
 INSERT INTO hisaab.decision_events(id,owner_id,entry_id,version,actor_auth_user_id,"before","after",reason)
 VALUES(gen_random_uuid(),p_owner,root,saved.version,NULL,coalesce(to_jsonb(previous),'{}'::jsonb),to_jsonb(saved),saved.reason);
 RETURN true;
END $$;

CREATE FUNCTION hisaab_api.auto_assign_entries(p_entry_ids uuid[],p_expected_owner uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner_ uuid:=hisaab.current_owner_id(); item record; assigned integer:=0;
BEGIN
 IF owner_ IS NULL OR owner_ IS DISTINCT FROM p_expected_owner THEN RAISE SQLSTATE '42501' USING MESSAGE='Reload your signed-in workspace'; END IF;
 IF p_entry_ids IS NULL OR cardinality(p_entry_ids)>50 OR array_position(p_entry_ids,NULL) IS NOT NULL THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose at most 50 entries'; END IF;
 -- Lock the whole batch before label locks; share ordering with backfill and settlement.
 PERFORM s.id FROM hisaab.statements s WHERE s.owner_id=owner_ AND EXISTS(
  SELECT 1 FROM hisaab.imports i JOIN hisaab.entries e ON e.import_id=i.id AND e.owner_id=i.owner_id
  WHERE i.owner_id=owner_ AND i.statement_id=s.id AND e.id=ANY(p_entry_ids)) ORDER BY s.id FOR UPDATE;
 -- Stable statement order prevents opposite-page lock ordering.
 FOR item IN SELECT e.id FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
  WHERE e.owner_id=owner_ AND e.id=ANY(p_entry_ids) ORDER BY i.statement_id,e.id LOOP
  IF hisaab.apply_entry_assignments(owner_,item.id) THEN assigned:=assigned+1; END IF;
 END LOOP;
 RETURN assigned;
END $$;

CREATE FUNCTION hisaab.assign_selected_source() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE item record;
BEGIN
 IF NEW.active_import_id IS NOT NULL AND NEW.active_import_id IS DISTINCT FROM OLD.active_import_id THEN
  FOR item IN SELECT id FROM hisaab.entries WHERE owner_id=NEW.owner_id AND import_id=NEW.active_import_id ORDER BY id LOOP
   PERFORM hisaab.apply_entry_assignments(NEW.owner_id,item.id);
  END LOOP;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assign_selected_source AFTER UPDATE OF active_import_id ON hisaab.statements FOR EACH ROW EXECUTE FUNCTION hisaab.assign_selected_source();
CREATE FUNCTION hisaab.assign_selected_entry() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN PERFORM hisaab.apply_entry_assignments(NEW.owner_id,NEW.id); RETURN NEW; END $$;
CREATE TRIGGER assign_selected_entry AFTER INSERT ON hisaab.entries FOR EACH ROW EXECUTE FUNCTION hisaab.assign_selected_entry();

REVOKE ALL ON hisaab.assignment_examples FROM PUBLIC;
DO $$ DECLARE f record; role_ text; BEGIN
 FOR f IN SELECT p.oid::regprocedure AS signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE (n.nspname='hisaab' AND p.proname IN ('merchant_key','save_entry_decision_without_learning','assignment_prediction','apply_entry_assignments','assign_selected_source','assign_selected_entry'))
 OR (n.nspname='hisaab_api' AND p.proname IN ('auto_assign_entries','save_entry_decision')) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
  FOREACH role_ IN ARRAY ARRAY['anon','authenticated'] LOOP
   IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_) THEN EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f.signature,role_); END IF;
  END LOOP;
 END LOOP;
 FOREACH role_ IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_) THEN EXECUTE format('REVOKE ALL ON hisaab.assignment_examples FROM %I',role_); END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT EXECUTE ON FUNCTION hisaab_api.auto_assign_entries(uuid[],uuid),hisaab_api.save_entry_decision(uuid,integer,jsonb) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
