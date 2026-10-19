-- Existing import RLS continues to scope all printed balance evidence.
CREATE VIEW hisaab_api.statement_bills WITH (security_invoker=true) AS
SELECT i.id,i.statement_id,i.card_id,s.card_label,s.bank,
 s.effective_statement_date AS statement_date,
 i.parsed_statement_date AS printed_statement_date,i.printed_balance
FROM hisaab_api.sources s JOIN hisaab.imports i ON i.id=s.id
WHERE s.state='selected';

REVOKE ALL ON hisaab_api.statement_bills FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON hisaab_api.statement_bills FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  GRANT SELECT (printed_balance) ON hisaab.imports TO authenticated;
  GRANT SELECT ON hisaab_api.statement_bills TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
