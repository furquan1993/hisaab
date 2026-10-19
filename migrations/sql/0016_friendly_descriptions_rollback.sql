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
 e.import_acknowledged,e.statement_date_override,e.decision_reason,e.original_transaction_time,NULL::text AS friendly_description,0::integer AS friendly_description_version
FROM hisaab.reviewed_entry_data e WHERE hisaab.import_state(e.import_id) IN ('selected','candidate');


DROP FUNCTION hisaab_api.save_friendly_description(uuid,integer,text);
