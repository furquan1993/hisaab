CREATE VIEW hisaab.funding_rows WITH(security_invoker=true) AS
SELECT e.owner_id,i.card_id,b.card_label,b.id,b.import_id,b.account_id,b.account_name,
 date_trunc('month',b.effective_statement_date)::date AS month,
 b.effective_currency AS currency,b.effective_entry_type AS entry_type,
 CASE WHEN b.effective_entry_type='payment' THEN 0::numeric
      WHEN b.effective_direction IN ('debit','credit') AND b.effective_amount IS NOT NULL
      THEN b.effective_amount::numeric * CASE b.effective_direction WHEN 'debit' THEN 1 ELSE -1 END
      ELSE 0::numeric END AS net,
 (b.needs_review OR (b.effective_entry_type<>'payment' AND
   (b.account_id IS NULL OR b.effective_currency IS NULL OR b.effective_amount IS NULL OR
    b.effective_direction IS NULL OR b.effective_entry_type='unknown'))) AS blocked,
 jsonb_build_array(b.id,b.import_id,b.logical_entry_id,b.decision_version,b.effective_statement_date,
   b.effective_amount,b.effective_direction,b.effective_currency,b.effective_entry_type,b.account_id,
   b.source_fingerprint,b.import_review_version,b.needs_review) AS evidence
FROM hisaab_api.entries b JOIN hisaab.entries e ON e.id=b.id
JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
WHERE b.is_selected;

CREATE VIEW hisaab_api.funding_attention WITH(security_invoker=true) AS
SELECT s.id,s.card_label,s.effective_statement_date,s.state,
 CASE WHEN s.effective_statement_date IS NULL THEN 'Statement month unknown'
      WHEN s.state='candidate' THEN 'Competing statement source' ELSE 'Statement coverage needs review' END AS reason
FROM hisaab_api.sources s WHERE s.state='candidate' OR (s.state='selected' AND
 (s.effective_statement_date IS NULL OR jsonb_array_length(s.unresolved_import_issues)>0 OR s.import_review_stale));

CREATE VIEW hisaab.funding_obligations WITH(security_invoker=true) AS
WITH grouped AS (
 SELECT owner_id,card_id,card_label,account_id,account_name,month,currency,
 sum(net) AS net,count(*) AS entry_count,
 encode(sha256(convert_to(jsonb_agg(evidence ORDER BY id)::text,'UTF8')),'hex') AS fingerprint
 FROM hisaab.funding_rows WHERE entry_type<>'payment'
 GROUP BY owner_id,card_id,card_label,account_id,account_name,month,currency
)
SELECT g.*,
 (EXISTS(SELECT 1 FROM hisaab.funding_rows r WHERE r.owner_id=g.owner_id AND r.card_id=g.card_id
    AND (r.month IS NOT DISTINCT FROM g.month OR r.month IS NULL) AND r.blocked)
  OR EXISTS(SELECT 1 FROM hisaab_api.sources s JOIN hisaab.imports i ON i.id=s.id
    WHERE i.owner_id=g.owner_id AND i.card_id=g.card_id AND s.state IN ('candidate','selected')
      AND (s.state='candidate' OR s.effective_statement_date IS NULL OR jsonb_array_length(s.unresolved_import_issues)>0 OR s.import_review_stale)
      AND (s.effective_statement_date IS NULL OR date_trunc('month',s.effective_statement_date)::date IS NOT DISTINCT FROM g.month))
 ) AS blocked
FROM grouped g;

CREATE VIEW hisaab_api.funding_totals WITH(security_invoker=true) AS
SELECT card_id,card_label,account_id,account_name,month,currency,net::text AS net,entry_count,fingerprint,blocked
FROM hisaab.funding_obligations;

REVOKE ALL ON hisaab.funding_rows,hisaab.funding_obligations,hisaab_api.funding_totals,hisaab_api.funding_attention FROM PUBLIC;
DO $$ DECLARE role_ text; BEGIN
 FOREACH role_ IN ARRAY ARRAY['anon','authenticated'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_) THEN
   EXECUTE format('REVOKE ALL ON hisaab.funding_rows,hisaab.funding_obligations,hisaab_api.funding_totals,hisaab_api.funding_attention FROM %I',role_);
  END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT SELECT ON hisaab.funding_rows,hisaab.funding_obligations,hisaab_api.funding_totals,hisaab_api.funding_attention TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
