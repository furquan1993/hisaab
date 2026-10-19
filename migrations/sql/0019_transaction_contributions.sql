-- Invoker views preserve owner RLS. Locks follow the existing contribution API.
-- https://www.postgresql.org/docs/17/sql-createview.html
-- https://www.postgresql.org/docs/17/explicit-locking.html
CREATE VIEW hisaab_api.funding_transaction_entries WITH(security_invoker=true) AS
WITH applications AS MATERIALIZED (
 SELECT c.owner_id,c.card_id,c.account_id,c.currency,a
 FROM hisaab.contributions c CROSS JOIN LATERAL jsonb_array_elements(c.applications::jsonb) a
 WHERE c.owner_id=(SELECT hisaab.current_owner_id())
), settled AS MATERIALIZED (
 SELECT e->>'logical_entry_id' AS logical_entry_id
 FROM applications CROSS JOIN LATERAL jsonb_array_elements(coalesce(a->'entries','[]'::jsonb)) e
)
SELECT r.card_id,r.account_id,r.currency,r.month,r.id,b.logical_entry_id,
 b.effective_description AS description,round(r.net,2)::text AS amount,
 b.effective_transaction_date AS transaction_date,
 EXISTS(SELECT 1 FROM settled s WHERE s.logical_entry_id=b.logical_entry_id::text) AS settled,
 EXISTS(SELECT 1 FROM applications a WHERE a.card_id=r.card_id AND a.account_id=r.account_id
   AND a.currency=r.currency AND a.a->>'month'=r.month::text AND NOT (a.a ? 'entries')) AS legacy_funded
FROM hisaab.funding_rows r JOIN hisaab_api.entries b ON b.id=r.id
WHERE r.owner_id=(SELECT hisaab.current_owner_id()) AND r.entry_type<>'payment' AND r.net>0 AND NOT r.blocked;

CREATE FUNCTION hisaab_api.record_transaction_contribution(p_id uuid,p_card_id uuid,p_account_id uuid,p_currency text,p_month date,
 p_entry_ids uuid[],p_received_on date,p_note text,p_expected_token text,p_expected_owner uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); receipt hisaab.contributions; wanted jsonb; preview jsonb;
 selected_ jsonb; applications_ jsonb; amount_ numeric;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 IF p_id IS NULL OR p_received_on IS NULL OR p_note IS NULL OR length(p_note)>2000 OR
   coalesce(cardinality(p_entry_ids),0)=0 OR cardinality(p_entry_ids)>1000 OR
   EXISTS(SELECT 1 FROM unnest(p_entry_ids) e WHERE e IS NULL) OR
   cardinality(p_entry_ids)<>(SELECT count(DISTINCT e) FROM unnest(p_entry_ids) e) THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Select unique whole transactions, a received date and a note of at most 2000 characters'; END IF;
 wanted:=jsonb_build_array(p_card_id,p_account_id,p_currency,p_month,
   (SELECT jsonb_agg(e ORDER BY e) FROM unnest(p_entry_ids) e),p_received_on,p_note,p_expected_token);
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
 IF p_expected_token IS DISTINCT FROM preview->>'token' THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Balances changed; reload and review'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(preview->'groups') g
   WHERE (g->>'blocked')::boolean OR (g->>'needs_review')::boolean) THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Resolve or confirm affected card months before contributing'; END IF;
 -- Resolve the complete selected set on the server; the caller never supplies amounts.
 SELECT jsonb_agg(to_jsonb(e) ORDER BY e.month,e.id) INTO selected_
 FROM hisaab_api.funding_transaction_entries e
 WHERE e.card_id=p_card_id AND e.account_id=p_account_id AND e.currency=p_currency AND e.month<=p_month
   AND e.id=ANY(p_entry_ids) AND NOT e.settled AND NOT e.legacy_funded;
 IF coalesce(jsonb_array_length(selected_),0)<>cardinality(p_entry_ids) THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Selected transactions are unavailable, already settled, or have earlier monthly contributions'; END IF;
 SELECT sum((e->>'amount')::numeric) INTO amount_ FROM jsonb_array_elements(selected_) e;
 IF amount_<=0 OR amount_>=1000000000000000000 THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Selected transaction total is out of range'; END IF;
 SELECT jsonb_agg(jsonb_build_object('month',m.month,'amount',round(m.amount,2)::text,
   'fingerprint',g->>'fingerprint','entries',m.entries) ORDER BY m.month) INTO applications_
 FROM (
   SELECT e->>'month' AS month,sum((e->>'amount')::numeric) AS amount,
     jsonb_agg(jsonb_build_object('entry_id',e->>'id','logical_entry_id',e->>'logical_entry_id',
       'description',e->>'description','amount',e->>'amount') ORDER BY e->>'id') AS entries
   FROM jsonb_array_elements(selected_) e GROUP BY e->>'month'
 ) m JOIN jsonb_array_elements(preview->'groups') g ON g->>'month'=m.month;
 INSERT INTO hisaab.contributions(id,owner_id,card_id,account_id,currency,month,amount,received_on,note,applications,request,actor_auth_user_id)
 VALUES(p_id,owner,p_card_id,p_account_id,p_currency,p_month,amount_,p_received_on,btrim(p_note),applications_,wanted,
   (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid) RETURNING * INTO receipt;
 RETURN (to_jsonb(receipt)-'owner_id'-'request')||jsonb_build_object('amount',receipt.amount::text);
EXCEPTION WHEN unique_violation THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Contribution request conflicts; reload before retrying';
END $$;

REVOKE ALL ON hisaab_api.funding_transaction_entries FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab_api.record_transaction_contribution(uuid,uuid,uuid,text,date,uuid[],date,text,text,uuid) FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON hisaab_api.funding_transaction_entries FROM anon;
  REVOKE ALL ON FUNCTION hisaab_api.record_transaction_contribution(uuid,uuid,uuid,text,date,uuid[],date,text,text,uuid) FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT SELECT ON hisaab_api.funding_transaction_entries TO authenticated;
  GRANT EXECUTE ON FUNCTION hisaab_api.record_transaction_contribution(uuid,uuid,uuid,text,date,uuid[],date,text,text,uuid) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
