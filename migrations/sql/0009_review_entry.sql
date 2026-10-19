CREATE FUNCTION hisaab_api.review_entry(
 p_entry_id uuid,p_expected_version integer,p_overrides jsonb,p_acknowledged jsonb,p_reason text,p_confirm_source boolean DEFAULT false
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); source hisaab.entries; previous hisaab.entry_decisions;
 saved hisaab.entry_decisions; root uuid; fingerprint text; changes jsonb; effective jsonb; item record; key_ text;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_version IS NULL OR p_expected_version<0 OR p_overrides IS NULL OR jsonb_typeof(p_overrides)<>'object' OR
    p_acknowledged IS NULL OR jsonb_typeof(p_acknowledged)<>'array' OR p_confirm_source IS NULL OR
    p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Provide valid review fields and a reason';
 END IF;
 SELECT e.* INTO source FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
 JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
 WHERE e.id=p_entry_id AND e.owner_id=owner FOR UPDATE OF s;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Entry is unavailable'; END IF;
 IF NOT EXISTS(SELECT 1 FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
   WHERE i.id=source.import_id AND i.owner_id=owner AND s.active_import_id=i.id) THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; reload before reviewing';
 END IF;
 root:=hisaab.logical_entry_id(source.id);fingerprint:=hisaab.entry_fingerprint(source);
 SELECT * INTO previous FROM hisaab.entry_decisions WHERE owner_id=owner AND entry_id=root FOR UPDATE;
 IF coalesce(previous.version,0)<>p_expected_version THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Entry changed; reload before saving'; END IF;
 IF previous.source_fingerprint IS NOT NULL AND previous.source_fingerprint<>fingerprint AND NOT p_confirm_source THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Previous corrections refer to different evidence; explicitly review the new source';
 END IF;
 IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_overrides) k WHERE k NOT IN ('transaction_date','transaction_time','description','amount','direction','currency','entry_type')) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Unsupported correction field';
 END IF;
 changes:=jsonb_strip_nulls(CASE WHEN previous.source_fingerprint=fingerprint THEN previous.overrides::jsonb ELSE '{}'::jsonb END||p_overrides);
 FOR item IN SELECT * FROM jsonb_each(changes) LOOP
   IF jsonb_typeof(item.value)<>'string' THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Corrections must use text; amounts must be decimal strings'; END IF;
   IF item.key='transaction_date' THEN
     IF item.value#>>'{}' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Use a valid ISO date'; END IF;
     changes:=jsonb_set(changes,'{transaction_date}',to_jsonb(to_char((item.value#>>'{}')::date,'YYYY-MM-DD')));
   ELSIF item.key='transaction_time' THEN
     IF item.value#>>'{}' !~ '^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$' OR split_part(item.value#>>'{}',':',1)::int>23 OR split_part(item.value#>>'{}',':',2)::int>59 OR coalesce(nullif(split_part(item.value#>>'{}',':',3),''),'0')::int>59 THEN
       RAISE SQLSTATE 'PT422' USING MESSAGE='Use a valid 24-hour time'; END IF;
     changes:=jsonb_set(changes,'{transaction_time}',to_jsonb((item.value#>>'{}')::time::text));
   ELSIF item.key='amount' THEN
     IF item.value#>>'{}' !~ '^[0-9]{1,18}([.][0-9]{1,2})?$' THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Use a nonnegative decimal amount with at most two places'; END IF;
     changes:=jsonb_set(changes,'{amount}',to_jsonb((item.value#>>'{}')::numeric(20,2)::text));
   ELSIF item.key='description' THEN
     IF length(btrim(item.value#>>'{}')) NOT BETWEEN 1 AND 2000 THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Provide a description of 1 to 2000 characters'; END IF;
   ELSIF item.key='direction' THEN
     IF item.value#>>'{}' NOT IN ('debit','credit') THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose debit or credit'; END IF;
   ELSIF item.key='currency' THEN
     IF item.value#>>'{}' !~ '^[A-Z]{3}$' THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Use a three-letter uppercase currency code'; END IF;
   ELSIF item.key='entry_type' THEN
     IF item.value#>>'{}' NOT IN ('purchase','payment','refund','cashback','fee','interest','tax','reversal','unknown') THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose a supported entry type'; END IF;
   END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_acknowledged) x WHERE jsonb_typeof(x)<>'string') OR
    (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_acknowledged))<>jsonb_array_length(p_acknowledged) THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid issue acknowledgements';
 END IF;
 FOR key_ IN SELECT jsonb_array_elements_text(p_acknowledged) LOOP
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(source.issues::jsonb) x WHERE hisaab.issue_key(x)=key_ AND NOT hisaab.critical_issue(x->>'code')) THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Correct missing or invalid facts instead of acknowledging them';
   END IF;
 END LOOP;
 effective:=hisaab.effective_values(source,NULL::hisaab.entry_decisions)||changes;
 IF (p_overrides ? 'entry_type' OR p_overrides ? 'direction') AND effective->>'entry_type' IN ('payment','cashback') AND effective->>'direction' IS DISTINCT FROM 'credit' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Payments and cashback require a verified credit direction';
 END IF;
 INSERT INTO hisaab.entry_decisions(id,owner_id,entry_id,overrides,acknowledged,source_fingerprint,version,reason)
 VALUES(gen_random_uuid(),owner,root,changes,p_acknowledged,fingerprint,p_expected_version+1,btrim(p_reason))
 ON CONFLICT(owner_id,entry_id) DO UPDATE SET overrides=excluded.overrides,acknowledged=excluded.acknowledged,
  source_fingerprint=excluded.source_fingerprint,version=excluded.version,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP
 RETURNING * INTO saved;
 INSERT INTO hisaab.decision_events(id,owner_id,entry_id,version,actor_auth_user_id,"before","after",reason)
 VALUES(gen_random_uuid(),owner,root,saved.version,(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid,
  coalesce(to_jsonb(previous),'{}'::jsonb),to_jsonb(saved),btrim(p_reason));
 RETURN to_jsonb(saved)-'owner_id';
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR numeric_value_out_of_range THEN
 RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid correction value';
END $$;
