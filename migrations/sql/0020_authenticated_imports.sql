-- Local parsing stays in Python. Ownership and all writes stay server-controlled.
-- https://supabase.com/docs/guides/database/functions#security-definer-vs-invoker
CREATE FUNCTION hisaab.import_summary(p_owner uuid,p_import uuid,p_status text)
RETURNS jsonb LANGUAGE sql SET search_path='' AS $$
 SELECT jsonb_build_object(
   'status',p_status,'owner_id',i.owner_id,'card_id',i.card_id,
   'statement_id',i.statement_id,'import_id',i.id,
   'transaction_count',(SELECT count(*) FROM hisaab.entries e WHERE e.owner_id=p_owner AND e.import_id=i.id),
   'review_issue_count',jsonb_array_length(i.issues::jsonb)+COALESCE((
     SELECT sum(jsonb_array_length(e.issues::jsonb)) FROM hisaab.entries e
     WHERE e.owner_id=p_owner AND e.import_id=i.id),0),
   'review_status',i.review_status,'selected_source',s.active_import_id IS NOT DISTINCT FROM i.id,
   'needs_review',jsonb_array_length(i.issues::jsonb)>0 OR EXISTS(
     SELECT 1 FROM hisaab.entries e WHERE e.owner_id=p_owner AND e.import_id=i.id
     AND jsonb_array_length(e.issues::jsonb)>0)
     OR s.active_import_id IS DISTINCT FROM i.id OR i.review_status='rejected')
 FROM hisaab.imports i JOIN hisaab.statements s ON s.owner_id=i.owner_id AND s.id=i.statement_id
 WHERE i.owner_id=p_owner AND i.id=p_import
$$;
REVOKE ALL ON FUNCTION hisaab.import_summary(uuid,uuid,text) FROM PUBLIC;

CREATE FUNCTION hisaab_api.find_pdf_import(p_card uuid,p_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); original hisaab.imports; chosen uuid;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF NOT EXISTS(SELECT 1 FROM hisaab.cards WHERE owner_id=owner AND id=p_card) THEN
   RAISE SQLSTATE 'PT404' USING MESSAGE='Card is unavailable';
 END IF;
 IF p_sha256 IS NULL OR p_sha256 !~ '^[0-9a-f]{64}$' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid PDF fingerprint';
 END IF;
 SELECT * INTO original FROM hisaab.imports WHERE owner_id=owner AND card_id=p_card
   AND file_sha256=p_sha256 AND source_import_id IS NULL;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT i.id INTO chosen FROM hisaab.imports i JOIN hisaab.statements s
   ON s.owner_id=i.owner_id AND s.active_import_id=i.id
   WHERE s.owner_id=owner AND s.id=original.statement_id AND i.file_sha256=p_sha256;
 RETURN hisaab.import_summary(owner,COALESCE(chosen,original.id),'duplicate');
END $$;

CREATE FUNCTION hisaab_api.import_statement(p_card uuid,p_statement jsonb,p_pdf_base64 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE
 owner uuid:=hisaab.current_owner_id(); card_bank text; pdf bytea; digest text;
 existing jsonb; matches uuid[]; statement_id uuid; import_id uuid:=gen_random_uuid();
 selected boolean:=false; extras jsonb:='[]'; row jsonb; source jsonb; issue jsonb;
 balance jsonb; pages integer; printed_date date; amount text; count_rows integer;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 -- Same lock as operator imports, card edits and review operations.
 SELECT bank INTO card_bank FROM hisaab.cards WHERE owner_id=owner AND id=p_card FOR UPDATE;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Card is unavailable'; END IF;
 IF p_pdf_base64 IS NULL OR length(p_pdf_base64)>27962028 THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='PDF must be at most 20 MiB';
 END IF;
 pdf:=decode(p_pdf_base64,'base64');
 IF octet_length(pdf)=0 OR octet_length(pdf)>20971520 OR substring(pdf FROM 1 FOR 5)<>convert_to('%PDF-','UTF8') THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid PDF snapshot';
 END IF;
 digest:=encode(sha256(pdf),'hex');
 IF jsonb_typeof(p_statement) IS DISTINCT FROM 'object'
   OR p_statement->>'source_sha256' IS DISTINCT FROM digest
   OR p_statement->>'input_kind' IS DISTINCT FROM 'pdf' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Extraction does not match the PDF snapshot';
 END IF;
 existing:=hisaab_api.find_pdf_import(p_card,digest);
 IF existing IS NOT NULL THEN RETURN existing; END IF;
 IF p_statement->>'bank' IS DISTINCT FROM card_bank THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Statement bank does not match the card';
 END IF;
 IF jsonb_typeof(p_statement->'source_name') IS DISTINCT FROM 'string'
   OR length(p_statement->>'source_name') NOT BETWEEN 1 AND 255
   OR p_statement->>'source_name' ~ '[/\\]'
   OR jsonb_typeof(p_statement->'page_count') IS DISTINCT FROM 'number'
   OR (p_statement->>'page_count') !~ '^[1-9][0-9]{0,4}$'
   OR jsonb_typeof(p_statement->'schema_version') IS DISTINCT FROM 'number'
   OR p_statement->>'schema_version' IS DISTINCT FROM '1'
   OR jsonb_typeof(p_statement->'parser_version') IS DISTINCT FROM 'string'
   OR length(p_statement->>'parser_version') NOT BETWEEN 1 AND 120
   OR jsonb_typeof(p_statement->'extractor_version') IS DISTINCT FROM 'string'
   OR length(p_statement->>'extractor_version') NOT BETWEEN 1 AND 120
   OR NOT (p_statement ? 'statement_date')
   OR jsonb_typeof(p_statement->'transactions') IS DISTINCT FROM 'array'
   OR jsonb_typeof(p_statement->'issues') IS DISTINCT FROM 'array' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid extraction metadata';
 END IF;
 pages:=(p_statement->>'page_count')::integer;
 IF p_statement->>'statement_date' IS NOT NULL AND
   (p_statement->>'statement_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid statement date';
 END IF;
 printed_date:=(p_statement->>'statement_date')::date;
 count_rows:=jsonb_array_length(p_statement->'transactions');
 IF count_rows>10000 THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Too many entries'; END IF;
 FOR row IN SELECT value FROM jsonb_array_elements(p_statement->'transactions') LOOP
   IF jsonb_typeof(row) IS DISTINCT FROM 'object'
     OR jsonb_typeof(row->'sequence') IS DISTINCT FROM 'number'
     OR (row->>'sequence') !~ '^[1-9][0-9]{0,4}$'
     OR (row->>'sequence')::integer>count_rows
     OR jsonb_typeof(row->'description') IS DISTINCT FROM 'string'
     OR jsonb_typeof(row->'section') IS DISTINCT FROM 'string'
     OR jsonb_typeof(row->'raw_date') IS DISTINCT FROM 'string'
     OR jsonb_typeof(row->'raw_time') IS DISTINCT FROM 'string'
     OR jsonb_typeof(row->'raw_amount') IS DISTINCT FROM 'string'
     OR jsonb_typeof(row->'issues') IS DISTINCT FROM 'array'
     OR NOT(row ?& ARRAY['amount','direction','currency','transaction_date','transaction_time'])
     OR row->>'entry_type' IS NULL
     OR row->>'entry_type' NOT IN ('purchase','payment','refund','cashback','fee','interest','tax','reversal','unknown') THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid transaction evidence';
   END IF;
   amount:=row->>'amount';
   IF amount IS NOT NULL AND (jsonb_typeof(row->'amount')<>'string' OR amount !~ '^[0-9]{1,18}(\.[0-9]{1,2})?$') THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Amounts must be exact nonnegative decimal strings';
   END IF;
   IF (row->>'direction' IS NOT NULL AND row->>'direction' NOT IN ('debit','credit'))
     OR (row->>'currency' IS NOT NULL AND row->>'currency' !~ '^[A-Z]{3}$')
     OR (row->>'transaction_date' IS NOT NULL AND row->>'transaction_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
     OR (row->>'transaction_time' IS NOT NULL AND row->>'transaction_time' !~ '^[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?$') THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid transaction facts';
   END IF;
 END LOOP;
 IF (SELECT count(DISTINCT value->>'sequence') FROM jsonb_array_elements(p_statement->'transactions'))<>count_rows THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Entry sequences must be unique';
 END IF;
 balance:=NULLIF(p_statement->'printed_balance','null'::jsonb);
 IF balance IS NOT NULL THEN
   IF jsonb_typeof(balance)<>'object' OR NOT(balance ?& ARRAY[
     'currency','previous_balance','payments_and_credits','charges','finance_charges','amount_due','source'])
     OR balance->>'currency' IS NULL OR balance->>'currency' !~ '^[A-Z]{3}$' THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid printed balance';
   END IF;
   FOREACH amount IN ARRAY ARRAY['previous_balance','payments_and_credits','charges','finance_charges','amount_due'] LOOP
     IF jsonb_typeof(balance->amount) IS DISTINCT FROM 'string'
       OR balance->>amount !~ '^[0-9]{1,18}(\.[0-9]{1,2})?$' THEN
       RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid printed balance amount';
     END IF;
   END LOOP;
 END IF;
 FOR source IN
   SELECT value->'source' FROM jsonb_array_elements(p_statement->'transactions')
   UNION ALL SELECT balance->'source' WHERE balance IS NOT NULL
 LOOP
   IF jsonb_typeof(source) IS DISTINCT FROM 'object'
     OR jsonb_typeof(source->'page') IS DISTINCT FROM 'number'
     OR (source->>'page') !~ '^[1-9][0-9]{0,4}$'
     OR (source->>'page')::integer>pages
     OR jsonb_typeof(source->'raw_text') IS DISTINCT FROM 'string'
     OR jsonb_typeof(source->'bbox') IS DISTINCT FROM 'array' THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid source provenance';
   END IF;
   IF jsonb_array_length(source->'bbox')<>4 OR EXISTS(
     SELECT 1 FROM jsonb_array_elements(source->'bbox') b WHERE jsonb_typeof(b)<>'number') THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid source position';
   END IF;
 END LOOP;
 FOR issue IN
   SELECT value FROM jsonb_array_elements(p_statement->'issues')
   UNION ALL SELECT j.value FROM jsonb_array_elements(p_statement->'transactions') r,
     LATERAL jsonb_array_elements(r->'issues') AS j(value)
 LOOP
   IF jsonb_typeof(issue) IS DISTINCT FROM 'object' OR jsonb_typeof(issue->'code') IS DISTINCT FROM 'string'
     OR length(issue->>'code') NOT BETWEEN 1 AND 120
     OR NOT(issue ? 'page') OR (issue->>'page' IS NOT NULL AND (
       (issue->>'page') !~ '^[1-9][0-9]{0,4}$' OR (issue->>'page')::integer>pages)) THEN
     RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid review issue';
   END IF;
 END LOOP;
 SELECT array_agg(id) INTO matches FROM (SELECT s.id FROM hisaab.statements s
   WHERE s.owner_id=owner AND s.card_id=p_card AND s.statement_date=printed_date
   ORDER BY s.id FOR UPDATE) locked;
 IF cardinality(matches)=1 THEN
   statement_id:=matches[1]; extras:='[{"code":"competing_statement_file","page": null}]';
 ELSE
   statement_id:=gen_random_uuid();
   INSERT INTO hisaab.statements(id,owner_id,card_id,statement_date)
     VALUES(statement_id,owner,p_card,printed_date);
   IF cardinality(matches)>1 THEN
     extras:=jsonb_build_array(jsonb_build_object('code','ambiguous_statement_match','page',NULL,'candidate_statement_ids',to_jsonb(matches)));
   ELSIF printed_date IS NULL THEN
     extras:='[{"code":"statement_match_unresolved","page": null}]';
   ELSE selected:=true;
   END IF;
 END IF;
 INSERT INTO hisaab.imports(id,owner_id,card_id,statement_id,source_filename,file_sha256,
   file_size_bytes,pdf_bytes,parsed_statement_date,page_count,parser_version,
   extractor_version,schema_version,review_status,issues,printed_balance)
 VALUES(import_id,owner,p_card,statement_id,p_statement->>'source_name',digest,
   octet_length(pdf),pdf,printed_date,pages,p_statement->>'parser_version',
   p_statement->>'extractor_version',1,'pending',p_statement->'issues'||extras,balance);
 FOR row IN SELECT value FROM jsonb_array_elements(p_statement->'transactions') LOOP
   INSERT INTO hisaab.entries(id,owner_id,import_id,sequence,transaction_date,transaction_time,
     description,amount,direction,currency,entry_type,section,raw_date,raw_time,raw_amount,
     source_page,source_bbox,source_raw_text,issues)
   VALUES(gen_random_uuid(),owner,import_id,(row->>'sequence')::integer,(row->>'transaction_date')::date,
     (row->>'transaction_time')::time,row->>'description',(row->>'amount')::numeric,
     row->>'direction',row->>'currency',row->>'entry_type',row->>'section',row->>'raw_date',
     row->>'raw_time',row->>'raw_amount',(row->'source'->>'page')::integer,
     row->'source'->'bbox',row->'source'->>'raw_text',row->'issues');
 END LOOP;
 IF selected THEN UPDATE hisaab.statements SET active_import_id=import_id WHERE id=statement_id AND owner_id=owner; END IF;
 RETURN hisaab.import_summary(owner,import_id,CASE WHEN selected THEN 'imported' ELSE 'review_candidate' END);
EXCEPTION
 WHEN invalid_text_representation OR invalid_parameter_value OR numeric_value_out_of_range
   OR datetime_field_overflow OR check_violation OR not_null_violation OR unique_violation THEN
   RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid statement extraction; nothing was imported';
END $$;

REVOKE ALL ON FUNCTION hisaab_api.find_pdf_import(uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION hisaab_api.import_statement(uuid,jsonb,text) FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
   REVOKE ALL ON FUNCTION hisaab.import_summary(uuid,uuid,text) FROM anon;
   REVOKE ALL ON FUNCTION hisaab_api.find_pdf_import(uuid,text) FROM anon;
   REVOKE ALL ON FUNCTION hisaab_api.import_statement(uuid,jsonb,text) FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
   REVOKE ALL ON FUNCTION hisaab.import_summary(uuid,uuid,text) FROM authenticated;
   GRANT EXECUTE ON FUNCTION hisaab_api.find_pdf_import(uuid,text) TO authenticated;
   GRANT EXECUTE ON FUNCTION hisaab_api.import_statement(uuid,jsonb,text) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
