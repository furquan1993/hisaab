CREATE VIEW hisaab_api.cards WITH (security_invoker=true) AS
 SELECT c.id,c.label,c.bank,c.last_four,c.version,
   EXISTS(SELECT 1 FROM hisaab.statements s WHERE s.owner_id=c.owner_id AND s.card_id=c.id) AS has_statements
 FROM hisaab.cards c;

CREATE FUNCTION hisaab_api.save_card(
 p_expected_owner uuid,p_label text,p_bank text,p_last_four text,
 p_id uuid,p_expected_version integer
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); previous hisaab.cards; saved hisaab.cards;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed';
 END IF;
 IF p_label IS NULL OR length(btrim(p_label)) NOT BETWEEN 1 AND 120
    OR p_bank IS NULL OR p_bank NOT IN ('hdfc','sbi','yes_bank')
    OR (p_last_four IS NOT NULL AND p_last_four !~ '^[0-9]{4}$') THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Use a card name, supported bank and optional four digits';
 END IF;
 IF p_id IS NULL THEN
   IF p_expected_version IS DISTINCT FROM 0 THEN
     RAISE SQLSTATE 'PT409' USING MESSAGE='Invalid new card version';
   END IF;
   INSERT INTO hisaab.cards(id,owner_id,label,bank,last_four)
     VALUES(gen_random_uuid(),owner,btrim(p_label),p_bank,p_last_four) RETURNING * INTO saved;
 ELSE
   SELECT * INTO previous FROM hisaab.cards WHERE owner_id=owner AND id=p_id FOR UPDATE;
   IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Card is unavailable'; END IF;
   IF previous.version IS DISTINCT FROM p_expected_version THEN
     RAISE SQLSTATE 'PT409' USING MESSAGE='Card changed; reload before saving';
   END IF;
   IF previous.bank IS DISTINCT FROM p_bank AND EXISTS(
     SELECT 1 FROM hisaab.statements WHERE owner_id=owner AND card_id=p_id
   ) THEN
     RAISE SQLSTATE 'PT409' USING MESSAGE='Bank cannot change after importing statements';
   END IF;
   UPDATE hisaab.cards SET label=btrim(p_label),bank=p_bank,last_four=p_last_four,version=version+1
     WHERE owner_id=owner AND id=p_id RETURNING * INTO saved;
 END IF;
 RETURN jsonb_build_object('id',saved.id,'label',saved.label,'bank',saved.bank,
   'last_four',saved.last_four,'version',saved.version,'has_statements',EXISTS(
     SELECT 1 FROM hisaab.statements WHERE owner_id=owner AND card_id=saved.id));
END $$;
REVOKE ALL ON hisaab_api.cards FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab_api.save_card(uuid,text,text,text,uuid,integer) FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
   REVOKE ALL ON hisaab_api.cards FROM anon;
   REVOKE ALL ON FUNCTION hisaab_api.save_card(uuid,text,text,text,uuid,integer) FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
   REVOKE ALL ON hisaab_api.cards FROM authenticated;
   GRANT SELECT ON hisaab_api.cards TO authenticated;
   REVOKE ALL ON FUNCTION hisaab_api.save_card(uuid,text,text,text,uuid,integer) FROM authenticated;
   GRANT EXECUTE ON FUNCTION hisaab_api.save_card(uuid,text,text,text,uuid,integer) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
