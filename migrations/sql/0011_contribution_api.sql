CREATE FUNCTION hisaab_api.funding_preview(p_card_id uuid,p_account_id uuid,p_currency text,p_month date,p_expected_owner uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 IF p_month IS NULL OR p_month<>date_trunc('month',p_month)::date OR p_currency IS NULL OR p_currency !~ '^[A-Z]{3}$' THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Choose a statement month and currency'; END IF;
 IF NOT EXISTS(SELECT 1 FROM hisaab.cards WHERE id=p_card_id AND owner_id=owner) OR
    NOT EXISTS(SELECT 1 FROM hisaab.accounts WHERE id=p_account_id AND owner_id=owner) THEN
  RAISE SQLSTATE 'PT404' USING MESSAGE='Funding group is unavailable'; END IF;
 RETURN hisaab.funding_preview_for_owner(owner,p_card_id,p_account_id,p_currency,p_month);
END $$;

CREATE FUNCTION hisaab_api.record_contribution(p_id uuid,p_card_id uuid,p_account_id uuid,p_currency text,p_month date,
 p_amount text,p_received_on date,p_note text,p_expected_token text,p_expected_owner uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); receipt hisaab.contributions; wanted jsonb; preview jsonb;
 total numeric; amount_ numeric; remaining numeric; part numeric; item jsonb; applications_ jsonb:='[]'::jsonb;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 IF p_id IS NULL OR p_received_on IS NULL OR p_note IS NULL OR length(p_note)>2000 OR
   (p_amount IS NOT NULL AND p_amount !~ '^[0-9]{1,18}([.][0-9]{1,2})?$') THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Use a positive decimal contribution, received date and note of at most 2000 characters'; END IF;
 wanted:=jsonb_build_array(p_card_id,p_account_id,p_currency,p_month,p_amount,p_received_on,p_note,p_expected_token);
 PERFORM pg_advisory_xact_lock(hashtextextended(owner::text||':'||p_id::text,0));
 SELECT * INTO receipt FROM hisaab.contributions WHERE id=p_id AND owner_id=owner;
 IF FOUND THEN
  IF receipt.request::jsonb<>wanted THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Request identifier already used with different input'; END IF;
  RETURN (to_jsonb(receipt)-'owner_id'-'request')||jsonb_build_object('amount',receipt.amount::text);
 END IF;
 PERFORM 1 FROM hisaab.cards WHERE id=p_card_id AND owner_id=owner FOR UPDATE;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Card is unavailable'; END IF;
 PERFORM 1 FROM hisaab.statements WHERE card_id=p_card_id AND owner_id=owner ORDER BY id FOR UPDATE;
 preview:=hisaab_api.funding_preview(p_card_id,p_account_id,p_currency,p_month,p_expected_owner);
 IF p_expected_token IS DISTINCT FROM preview->>'token' THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Balances changed; reload and review before contributing'; END IF;
 IF jsonb_array_length(preview->'groups')=0 OR EXISTS(SELECT 1 FROM jsonb_array_elements(preview->'groups') g
   WHERE (g->>'blocked')::boolean OR (g->>'needs_review')::boolean) THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Resolve or confirm the affected card months before contributing'; END IF;
 SELECT coalesce(sum((g->>'outstanding')::numeric),0) INTO total FROM jsonb_array_elements(preview->'groups') g;
 amount_:=CASE WHEN p_amount IS NULL THEN total ELSE p_amount::numeric END;
 IF amount_<=0 OR amount_>total OR amount_>=1000000000000000000 THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Contribution must be positive and no greater than this card/account/currency outstanding balance'; END IF;
 remaining:=amount_;
 FOR item IN SELECT value FROM jsonb_array_elements(preview->'groups') ORDER BY value->>'month' LOOP
  part:=least(remaining,(item->>'outstanding')::numeric);
  IF part>0 THEN
   applications_:=applications_||jsonb_build_array(jsonb_build_object('month',item->>'month','amount',round(part,2)::text,'fingerprint',item->>'fingerprint'));
   remaining:=remaining-part;
  END IF;
 END LOOP;
 IF remaining<>0 THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Allocation changed; reload before retrying'; END IF;
 INSERT INTO hisaab.contributions(id,owner_id,card_id,account_id,currency,month,amount,received_on,note,applications,request,actor_auth_user_id)
 VALUES(p_id,owner,p_card_id,p_account_id,p_currency,p_month,amount_,p_received_on,btrim(p_note),applications_,wanted,
   (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid) RETURNING * INTO receipt;
 RETURN (to_jsonb(receipt)-'owner_id'-'request')||jsonb_build_object('amount',receipt.amount::text);
EXCEPTION WHEN unique_violation THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Contribution request conflicts; reload before retrying';
END $$;

CREATE FUNCTION hisaab_api.confirm_funding(p_card_id uuid,p_account_id uuid,p_currency text,p_month date,
 p_reason text,p_expected_token text,p_expected_owner uuid,p_through_month date DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); preview jsonb; target jsonb; saved hisaab.funding_confirmations;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 IF p_reason IS NULL OR length(btrim(p_reason)) NOT BETWEEN 1 AND 2000 THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Provide a review reason'; END IF;
 PERFORM 1 FROM hisaab.cards WHERE id=p_card_id AND owner_id=owner FOR UPDATE;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Card is unavailable'; END IF;
 PERFORM 1 FROM hisaab.statements WHERE card_id=p_card_id AND owner_id=owner ORDER BY id FOR UPDATE;
 IF p_through_month IS NOT NULL AND p_through_month<p_month THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Review month is outside the preview'; END IF;
 preview:=hisaab_api.funding_preview(p_card_id,p_account_id,p_currency,coalesce(p_through_month,p_month),p_expected_owner);
 IF p_expected_token IS DISTINCT FROM preview->>'token' THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Balances changed; reload and review'; END IF;
 SELECT value INTO target FROM jsonb_array_elements(preview->'groups') WHERE value->>'month'=p_month::text;
 IF target IS NULL THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Month is unavailable'; END IF;
 IF (target->>'blocked')::boolean THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Resolve source issues before confirming'; END IF;
 INSERT INTO hisaab.funding_confirmations(id,owner_id,card_id,account_id,currency,month,fingerprint,reason,actor_auth_user_id)
 VALUES(gen_random_uuid(),owner,p_card_id,p_account_id,p_currency,p_month,target->>'fingerprint',btrim(p_reason),
   (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid) RETURNING * INTO saved;
 RETURN to_jsonb(saved)-'owner_id';
END $$;

REVOKE ALL ON hisaab.contributions,hisaab.funding_confirmations,hisaab.contribution_applications,hisaab.funding_balances,
 hisaab_api.funding_groups,hisaab_api.contributions,hisaab_api.funding_entries FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab.funding_preview_for_owner(uuid,uuid,uuid,text,date),
 hisaab_api.funding_preview(uuid,uuid,text,date,uuid),hisaab_api.record_contribution(uuid,uuid,uuid,text,date,text,date,text,text,uuid),
 hisaab_api.confirm_funding(uuid,uuid,text,date,text,text,uuid,date) FROM PUBLIC;
DO $$ DECLARE role_ text; BEGIN
 FOREACH role_ IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_) THEN
   EXECUTE format('REVOKE ALL ON hisaab.contributions,hisaab.funding_confirmations,hisaab.contribution_applications,hisaab.funding_balances,hisaab_api.funding_groups,hisaab_api.contributions,hisaab_api.funding_entries FROM %I',role_);
   EXECUTE format('REVOKE ALL ON FUNCTION hisaab.funding_preview_for_owner(uuid,uuid,uuid,text,date),hisaab_api.funding_preview(uuid,uuid,text,date,uuid),hisaab_api.record_contribution(uuid,uuid,uuid,text,date,text,date,text,text,uuid),hisaab_api.confirm_funding(uuid,uuid,text,date,text,text,uuid,date) FROM %I',role_);
  END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT SELECT ON hisaab.contributions,hisaab.funding_confirmations,hisaab.contribution_applications,hisaab.funding_balances,hisaab_api.funding_groups,hisaab_api.contributions,hisaab_api.funding_entries TO authenticated;
  GRANT EXECUTE ON FUNCTION hisaab_api.funding_preview(uuid,uuid,text,date,uuid),
    hisaab_api.record_contribution(uuid,uuid,uuid,text,date,text,date,text,text,uuid),hisaab_api.confirm_funding(uuid,uuid,text,date,text,text,uuid,date) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
