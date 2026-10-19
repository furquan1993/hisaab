CREATE VIEW hisaab.import_review_data WITH (security_invoker=true) AS
WITH context AS (
 SELECT i.id,i.owner_id,i.parsed_statement_date AS printed_statement_date,i.issues::jsonb AS raw_import_issues,
  (s.active_import_id IS NOT DISTINCT FROM i.id) AS is_selected,
  coalesce(r.version,0) AS import_review_version,r.reason AS import_review_reason,
  (r.id IS NOT NULL AND r.source_fingerprint<>hisaab.coverage_fingerprint(i.file_sha256,i.page_count,i.parsed_statement_date,i.issues::jsonb)) AS import_review_stale,
  CASE WHEN r.source_fingerprint=hisaab.coverage_fingerprint(i.file_sha256,i.page_count,i.parsed_statement_date,i.issues::jsonb) THEN r.acknowledged::jsonb ELSE '[]'::jsonb END AS import_acknowledged,
  CASE WHEN r.source_fingerprint=hisaab.coverage_fingerprint(i.file_sha256,i.page_count,i.parsed_statement_date,i.issues::jsonb) THEN r.statement_date_override END AS statement_date_override
 FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
 LEFT JOIN LATERAL(SELECT * FROM hisaab.import_reviews r WHERE r.owner_id=i.owner_id AND r.import_id=coalesce(i.source_import_id,i.id) ORDER BY r.version DESC LIMIT 1) r ON true
), effective AS (
 SELECT context.*,coalesce(statement_date_override,printed_statement_date) AS effective_statement_date FROM context
)
SELECT effective.*,hisaab.unresolved_issues(raw_import_issues,jsonb_build_object(
 'statement_date',effective_statement_date,'statement_date_confirmed',statement_date_override IS NOT NULL,'is_selected',is_selected),import_acknowledged) AS unresolved_import_issues
FROM effective;

CREATE VIEW hisaab.reviewed_entry_data WITH (security_invoker=true) AS
WITH context AS (
 SELECT b.*,hisaab.logical_entry_id(e.id) AS logical_entry_id,coalesce(d.version,0) AS decision_version,
  d.category_id,c.name AS category_name,d.account_id,a.name AS account_name,
  coalesce(d.overrides::jsonb,'{}'::jsonb) AS overrides,coalesce(d.acknowledged::jsonb,'[]'::jsonb) AS acknowledged,
  d.source_fingerprint,d.updated_at AS decision_updated_at,d.reason AS decision_reason,
  (d.source_fingerprint IS NOT NULL AND d.source_fingerprint<>hisaab.entry_fingerprint(e)) AS review_stale,
  CASE WHEN d.source_fingerprint=hisaab.entry_fingerprint(e) THEN d.overrides::jsonb ELSE '{}'::jsonb END AS applied_overrides,
  CASE WHEN d.source_fingerprint=hisaab.entry_fingerprint(e) THEN d.acknowledged::jsonb ELSE '[]'::jsonb END AS applied_acknowledged,
  e.transaction_time AS original_transaction_time,hisaab.effective_values(e,d) AS effective_values,
  i.effective_statement_date,i.printed_statement_date,i.import_review_version,i.import_review_reason,
  i.import_review_stale,i.import_acknowledged,i.statement_date_override,i.unresolved_import_issues
 FROM hisaab.all_extracted_entries b JOIN hisaab.entries e ON e.id=b.id
 JOIN hisaab.import_review_data i ON i.id=e.import_id AND i.owner_id=e.owner_id
 LEFT JOIN hisaab.entry_decisions d ON d.entry_id=hisaab.logical_entry_id(e.id) AND d.owner_id=e.owner_id
 LEFT JOIN hisaab.categories c ON c.id=d.category_id AND c.owner_id=d.owner_id
 LEFT JOIN hisaab.accounts a ON a.id=d.account_id AND a.owner_id=d.owner_id
), issues AS (
 SELECT context.*,hisaab.unresolved_issues(entry_issues,effective_values,applied_acknowledged) AS unresolved_entry_issues FROM context
)
SELECT issues.*,(NOT is_selected OR effective_values->>'transaction_date' IS NULL OR effective_statement_date IS NULL OR
 effective_values->>'amount' IS NULL OR effective_values->>'currency' IS NULL OR effective_values->>'direction' IS NULL OR
 length(btrim(coalesce(effective_values->>'description','')))=0 OR effective_values->>'entry_type'='unknown' OR
 (effective_values->>'entry_type' IN ('payment','cashback') AND effective_values->>'direction' IS DISTINCT FROM 'credit') OR
 jsonb_array_length(unresolved_entry_issues)>0 OR jsonb_array_length(unresolved_import_issues)>0 OR review_stale OR import_review_stale) AS reviewed_needs_review
FROM issues;

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
 e.import_acknowledged,e.statement_date_override,e.decision_reason,e.original_transaction_time
FROM hisaab.reviewed_entry_data e WHERE hisaab.import_state(e.import_id) IN ('selected','candidate');

CREATE OR REPLACE VIEW hisaab_api.sources WITH (security_invoker=true) AS
SELECT i.id,i.statement_id,c.label AS card_label,c.bank,s.statement_date,i.source_import_id,
 i.source_filename,i.file_sha256,i.parsed_statement_date,i.page_count,i.parser_version,i.extractor_version,
 i.issues::jsonb AS issues,hisaab.import_state(i.id) AS state,i.created_at,
 (SELECT count(*) FROM hisaab.entries e WHERE e.import_id=i.id AND e.owner_id=i.owner_id) AS entry_count,
 r.effective_statement_date,r.import_review_version,r.import_acknowledged,r.statement_date_override,r.import_review_stale,r.unresolved_import_issues
FROM hisaab.imports i JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
JOIN hisaab.cards c ON c.id=i.card_id AND c.owner_id=i.owner_id
JOIN hisaab.import_review_data r ON r.id=i.id AND r.owner_id=i.owner_id;

CREATE VIEW hisaab_api.import_review_history WITH (security_invoker=true) AS
SELECT id,import_id,reviewed_import_id,version,source_fingerprint,acknowledged::jsonb AS acknowledged,
 statement_date_override,reason,actor_auth_user_id,created_at FROM hisaab.import_reviews;
