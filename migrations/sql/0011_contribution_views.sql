CREATE VIEW hisaab.contribution_applications WITH(security_invoker=true) AS
SELECT c.owner_id,c.id,c.created_at,c.card_id,c.account_id,c.currency,
 (a->>'month')::date AS month,(a->>'amount')::numeric AS amount,a->>'fingerprint' AS fingerprint
FROM hisaab.contributions c CROSS JOIN LATERAL jsonb_array_elements(c.applications::jsonb) a;

CREATE VIEW hisaab.funding_balances WITH(security_invoker=true) AS
WITH keys AS (
 SELECT owner_id,card_id,account_id,currency,month FROM hisaab.funding_obligations
 UNION SELECT owner_id,card_id,account_id,currency,month FROM hisaab.contribution_applications
 UNION SELECT owner_id,card_id,account_id,currency,month FROM hisaab.funding_confirmations
), balances AS (
 SELECT k.*,c.label AS card_label,a.name AS account_name,coalesce(o.net,0) AS net,coalesce(o.entry_count,0) AS entry_count,
 coalesce(o.fingerprint,encode(sha256(convert_to(jsonb_build_array(k.card_id,k.account_id,k.currency,k.month,'empty')::text,'UTF8')),'hex')) AS fingerprint,
 coalesce(p.received,0) AS received,
 coalesce(o.blocked,false) OR k.account_id IS NULL OR k.currency IS NULL OR k.month IS NULL AS blocked,
 e.fingerprint AS acknowledged_fingerprint
 FROM keys k JOIN hisaab.cards c ON c.id=k.card_id AND c.owner_id=k.owner_id
 LEFT JOIN hisaab.accounts a ON a.id=k.account_id AND a.owner_id=k.owner_id
 LEFT JOIN hisaab.funding_obligations o ON o.owner_id=k.owner_id AND o.card_id=k.card_id
   AND o.account_id IS NOT DISTINCT FROM k.account_id AND o.currency IS NOT DISTINCT FROM k.currency AND o.month IS NOT DISTINCT FROM k.month
 LEFT JOIN LATERAL(SELECT sum(p.amount) AS received FROM hisaab.contribution_applications p
   WHERE p.owner_id=k.owner_id AND p.card_id=k.card_id AND p.account_id=k.account_id AND p.currency=k.currency AND p.month=k.month) p ON true
 LEFT JOIN LATERAL(
   SELECT events.fingerprint FROM (
    SELECT p.created_at,p.id,p.fingerprint FROM hisaab.contribution_applications p
    WHERE p.owner_id=k.owner_id AND p.card_id=k.card_id AND p.account_id=k.account_id AND p.currency=k.currency AND p.month=k.month
    UNION ALL SELECT f.created_at,f.id,f.fingerprint FROM hisaab.funding_confirmations f
    WHERE f.owner_id=k.owner_id AND f.card_id=k.card_id AND f.account_id=k.account_id AND f.currency=k.currency AND f.month=k.month
   ) events ORDER BY events.created_at DESC,events.id DESC LIMIT 1
 ) e ON true
)
SELECT balances.*,greatest(greatest(net,0)-received,0) AS outstanding,
 greatest(received-greatest(net,0),0) AS credit,
 acknowledged_fingerprint IS NOT NULL AND acknowledged_fingerprint<>fingerprint AS needs_review
FROM balances;

CREATE VIEW hisaab_api.funding_groups WITH(security_invoker=true) AS
SELECT card_id,card_label,account_id,account_name,month,currency,round(net,2)::text AS net,
 round(received,2)::text AS received,round(outstanding,2)::text AS outstanding,round(credit,2)::text AS credit,
 entry_count,fingerprint,blocked,needs_review FROM hisaab.funding_balances;
CREATE VIEW hisaab_api.funding_entries WITH(security_invoker=true) AS
SELECT r.card_id,r.account_id,r.currency,r.month,b.id,b.description,b.effective_description,
 b.effective_amount,b.effective_direction,b.effective_entry_type,b.effective_transaction_date
FROM hisaab.funding_rows r JOIN hisaab_api.entries b ON b.id=r.id WHERE r.entry_type<>'payment';
CREATE VIEW hisaab_api.contributions WITH(security_invoker=true) AS
SELECT id,card_id,account_id,currency,month,amount::text AS amount,received_on,note,
 applications::jsonb AS applications,actor_auth_user_id,created_at FROM hisaab.contributions;

CREATE FUNCTION hisaab.funding_preview_for_owner(p_owner uuid,p_card uuid,p_account uuid,p_currency text,p_month date)
RETURNS jsonb LANGUAGE sql STABLE SET search_path='' AS $$
 WITH groups AS (
 SELECT * FROM hisaab.funding_balances WHERE owner_id=p_owner AND card_id=p_card AND account_id=p_account
   AND currency=p_currency AND month<=p_month
 ), payload AS (
 SELECT coalesce(jsonb_agg(jsonb_build_object('month',month,'net',round(net,2)::text,
   'received',round(received,2)::text,'outstanding',round(outstanding,2)::text,'credit',round(credit,2)::text,
   'fingerprint',fingerprint,'blocked',blocked,'needs_review',needs_review) ORDER BY month),'[]'::jsonb) AS groups FROM groups
 ) SELECT jsonb_build_object('groups',groups,'token',encode(sha256(convert_to(groups::text,'UTF8')),'hex')) FROM payload
$$;
