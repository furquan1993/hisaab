CREATE OR REPLACE VIEW hisaab_api.entries WITH (security_invoker=true) AS
SELECT e.id,e.import_id,e.statement_id,e.card_label,e.bank,e.statement_date,e.transaction_date,e.description,e.amount,
 e.direction,e.currency,e.entry_type,e.sequence,e.is_selected,e.reviewed_needs_review AS needs_review,
 e.entry_issues,e.import_issues,e.review_status,e.logical_entry_id,e.decision_version,e.category_id,e.category_name,e.account_id,e.account_name,
 e.overrides,e.acknowledged,e.source_fingerprint,e.decision_updated_at,
 e.effective_values->>'transaction_date' AS effective_transaction_date,e.effective_values->>'transaction_time' AS effective_transaction_time,
 e.effective_values->>'description' AS effective_description,e.effective_values->>'amount' AS effective_amount,
 e.effective_values->>'direction' AS effective_direction,e.effective_values->>'currency' AS effective_currency,e.effective_values->>'entry_type' AS effective_entry_type,
 e.effective_statement_date,e.printed_statement_date,e.review_stale,e.applied_overrides,e.applied_acknowledged,
 e.unresolved_entry_issues,e.unresolved_import_issues,e.import_review_version,e.import_review_reason,e.import_review_stale,
 e.import_acknowledged,e.statement_date_override,e.decision_reason,e.original_transaction_time,
 d.description AS friendly_description,coalesce(d.version,0) AS friendly_description_version
FROM hisaab.reviewed_entry_data e
LEFT JOIN LATERAL (SELECT description,version FROM hisaab.entry_descriptions
 WHERE owner_id=hisaab.current_owner_id() AND entry_id=e.logical_entry_id ORDER BY version DESC LIMIT 1) d ON true
WHERE hisaab.import_state(e.import_id) IN ('selected','candidate');

CREATE OR REPLACE VIEW hisaab_api.funding_entries WITH(security_invoker=true) AS
SELECT i.card_id,b.account_id,b.effective_currency AS currency,
 date_trunc('month',b.effective_statement_date)::date AS month,
 b.id,b.description,b.effective_description,b.effective_amount,
 b.effective_direction,b.effective_entry_type,b.effective_transaction_date,b.friendly_description
FROM hisaab_api.entries b JOIN hisaab.imports i ON i.id=b.import_id
WHERE b.is_selected AND b.effective_entry_type<>'payment';

-- Serialize with source acceptance, while retaining independent description versions.
-- https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY
CREATE FUNCTION hisaab_api.save_friendly_description(p_entry_id uuid,p_expected_version integer,p_description text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner_ uuid:=hisaab.current_owner_id(); source hisaab.entries;
 previous hisaab.entry_descriptions; saved hisaab.entry_descriptions; root uuid;
 value_ text:=nullif(btrim(p_description),'');
BEGIN
 IF owner_ IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_version IS NULL OR p_expected_version<0 OR length(value_)>500 THEN
  RAISE SQLSTATE 'PT422' USING MESSAGE='Use a description of at most 500 characters and a valid version'; END IF;
 SELECT e.* INTO source FROM hisaab.entries e JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
 JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
 WHERE e.id=p_entry_id AND e.owner_id=owner_ FOR UPDATE OF s;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Entry is unavailable'; END IF;
 IF NOT EXISTS(SELECT 1 FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
  WHERE i.id=source.import_id AND i.owner_id=owner_ AND s.active_import_id=i.id) THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; reload before saving'; END IF;
 root:=hisaab.logical_entry_id(source.id);
 SELECT * INTO previous FROM hisaab.entry_descriptions WHERE owner_id=owner_ AND entry_id=root ORDER BY version DESC LIMIT 1;
 IF coalesce(previous.version,0)<>p_expected_version THEN
  RAISE SQLSTATE 'PT409' USING MESSAGE='Description changed; reload before saving'; END IF;
 IF previous.description IS NOT DISTINCT FROM value_ THEN
  RETURN jsonb_build_object('friendly_description',value_,'friendly_description_version',coalesce(previous.version,0));
 END IF;
 INSERT INTO hisaab.entry_descriptions(id,owner_id,entry_id,version,description,actor_auth_user_id)
 VALUES(gen_random_uuid(),owner_,root,p_expected_version+1,value_,
  (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid) RETURNING * INTO saved;
 RETURN jsonb_build_object('friendly_description',saved.description,'friendly_description_version',saved.version);
END $$;

ALTER TABLE hisaab.entry_descriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY browser_read ON hisaab.entry_descriptions FOR SELECT USING(owner_id=(SELECT hisaab.current_owner_id()));
REVOKE ALL ON hisaab.entry_descriptions FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab_api.save_friendly_description(uuid,integer,text) FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON hisaab.entry_descriptions FROM anon;
  REVOKE ALL ON FUNCTION hisaab_api.save_friendly_description(uuid,integer,text) FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  REVOKE ALL ON hisaab.entry_descriptions FROM authenticated;
  GRANT SELECT ON hisaab.entry_descriptions TO authenticated;
  GRANT EXECUTE ON FUNCTION hisaab_api.save_friendly_description(uuid,integer,text) TO authenticated;
 END IF;
END $$;

-- Keep the spending explorer's frozen SELECT * projection in sync, appending
-- display fields after its existing group columns to preserve the API contract.
CREATE OR REPLACE VIEW hisaab_api.spending_entries WITH (security_invoker=true) AS
 SELECT e.id,e.import_id,e.statement_id,e.card_label,e.bank,
 e.statement_date,e.transaction_date,e.description,e.amount,e.direction,
 e.currency,e.entry_type,e.sequence,e.is_selected,e.needs_review,
 e.entry_issues,e.import_issues,e.review_status,e.logical_entry_id,e.decision_version,
 e.category_id,e.category_name,e.account_id,e.account_name,e.overrides,
 e.acknowledged,e.source_fingerprint,e.decision_updated_at,e.effective_transaction_date,e.effective_transaction_time,
 e.effective_description,e.effective_amount,e.effective_direction,e.effective_currency,e.effective_entry_type,
 e.effective_statement_date,e.printed_statement_date,e.review_stale,e.applied_overrides,e.applied_acknowledged,
 e.unresolved_entry_issues,e.unresolved_import_issues,e.import_review_version,e.import_review_reason,e.import_review_stale,
 e.import_acknowledged,e.statement_date_override,e.decision_reason,e.original_transaction_time,
 a.group_id,g.name AS group_name,coalesce(a.version,0) AS group_version,
 e.friendly_description,e.friendly_description_version
 FROM hisaab_api.entries e
 LEFT JOIN hisaab.spending_assignments a ON a.entry_id=e.logical_entry_id AND a.owner_id=hisaab.current_owner_id()
 LEFT JOIN hisaab.spending_groups g ON g.id=a.group_id AND g.owner_id=a.owner_id
 WHERE e.is_selected;
NOTIFY pgrst,'reload schema';
