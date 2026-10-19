-- Evaluate expensive reviewed evidence once per authenticated owner, not once
-- for every account/month join. These are optimization fences, not cached data.
-- https://www.postgresql.org/docs/17/queries-with.html#QUERIES-WITH-CTE-MATERIALIZATION
CREATE OR REPLACE VIEW hisaab.funding_obligations WITH(security_invoker=true) AS
WITH rows AS MATERIALIZED (
 SELECT * FROM hisaab.funding_rows WHERE owner_id=(SELECT hisaab.current_owner_id())
), sources AS MATERIALIZED (
 SELECT i.owner_id,i.card_id,s.effective_statement_date,s.state,s.unresolved_import_issues,s.import_review_stale
 FROM hisaab_api.sources s JOIN hisaab.imports i ON i.id=s.id
 WHERE i.owner_id=(SELECT hisaab.current_owner_id())
), grouped AS (
 SELECT owner_id,card_id,card_label,account_id,account_name,month,currency,
 sum(net) AS net,count(*) AS entry_count,
 encode(sha256(convert_to(jsonb_agg(evidence ORDER BY id)::text,'UTF8')),'hex') AS fingerprint
 FROM rows WHERE entry_type<>'payment'
 GROUP BY owner_id,card_id,card_label,account_id,account_name,month,currency
)
SELECT g.*,
 (EXISTS(SELECT 1 FROM rows r WHERE r.owner_id=g.owner_id AND r.card_id=g.card_id
    AND (r.month IS NOT DISTINCT FROM g.month OR r.month IS NULL) AND r.blocked)
  OR EXISTS(SELECT 1 FROM sources s
    WHERE s.owner_id=g.owner_id AND s.card_id=g.card_id AND s.state IN ('candidate','selected')
      AND (s.state='candidate' OR s.effective_statement_date IS NULL OR jsonb_array_length(s.unresolved_import_issues)>0 OR s.import_review_stale)
      AND (s.effective_statement_date IS NULL OR date_trunc('month',s.effective_statement_date)::date IS NOT DISTINCT FROM g.month))
 ) AS blocked
FROM grouped g;

CREATE OR REPLACE VIEW hisaab.funding_balances WITH(security_invoker=true) AS
WITH obligations AS MATERIALIZED (
 SELECT * FROM hisaab.funding_obligations WHERE owner_id=(SELECT hisaab.current_owner_id())
), applications AS MATERIALIZED (
 SELECT * FROM hisaab.contribution_applications WHERE owner_id=(SELECT hisaab.current_owner_id())
), confirmations AS MATERIALIZED (
 SELECT * FROM hisaab.funding_confirmations WHERE owner_id=(SELECT hisaab.current_owner_id())
), payments AS (
 SELECT owner_id,card_id,account_id,currency,month,sum(amount) AS received
 FROM applications GROUP BY owner_id,card_id,account_id,currency,month
), latest_events AS (
 SELECT DISTINCT ON(owner_id,card_id,account_id,currency,month)
 owner_id,card_id,account_id,currency,month,fingerprint
 FROM (
  SELECT owner_id,card_id,account_id,currency,month,created_at,id,fingerprint FROM applications
  UNION ALL SELECT owner_id,card_id,account_id,currency,month,created_at,id,fingerprint FROM confirmations
 ) events
 ORDER BY owner_id,card_id,account_id,currency,month,created_at DESC,id DESC
), keys AS (
 SELECT owner_id,card_id,account_id,currency,month FROM obligations
 UNION SELECT owner_id,card_id,account_id,currency,month FROM applications
 UNION SELECT owner_id,card_id,account_id,currency,month FROM confirmations
), balances AS (
 SELECT k.*,c.label AS card_label,a.name AS account_name,coalesce(o.net,0) AS net,coalesce(o.entry_count,0) AS entry_count,
 coalesce(o.fingerprint,encode(sha256(convert_to(jsonb_build_array(k.card_id,k.account_id,k.currency,k.month,'empty')::text,'UTF8')),'hex')) AS fingerprint,
 coalesce(p.received,0) AS received,
 coalesce(o.blocked,false) OR k.account_id IS NULL OR k.currency IS NULL OR k.month IS NULL AS blocked,
 e.fingerprint AS acknowledged_fingerprint
 FROM keys k JOIN hisaab.cards c ON c.id=k.card_id AND c.owner_id=k.owner_id
 LEFT JOIN hisaab.accounts a ON a.id=k.account_id AND a.owner_id=k.owner_id
 LEFT JOIN obligations o ON o.owner_id=k.owner_id AND o.card_id=k.card_id
   AND o.account_id IS NOT DISTINCT FROM k.account_id AND o.currency IS NOT DISTINCT FROM k.currency AND o.month IS NOT DISTINCT FROM k.month
 LEFT JOIN payments p ON p.owner_id=k.owner_id AND p.card_id=k.card_id AND p.account_id=k.account_id AND p.currency=k.currency AND p.month=k.month
 LEFT JOIN latest_events e ON e.owner_id=k.owner_id AND e.card_id=k.card_id AND e.account_id=k.account_id AND e.currency=k.currency AND e.month=k.month
)
SELECT balances.*,greatest(greatest(net,0)-received,0) AS outstanding,
 greatest(received-greatest(net,0),0) AS credit,
 acknowledged_fingerprint IS NOT NULL AND acknowledged_fingerprint<>fingerprint AS needs_review
FROM balances;
NOTIFY pgrst,'reload schema';
