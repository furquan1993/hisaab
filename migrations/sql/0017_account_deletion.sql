-- Account tombstones keep immutable receipts valid; all current assignments clear.
CREATE OR REPLACE VIEW hisaab_api.labels WITH (security_invoker=true) AS
 SELECT id,'category'::text AS kind,name,is_archived,version FROM hisaab.categories
 UNION ALL SELECT id,'account',name,is_archived,version FROM hisaab.accounts WHERE deleted_at IS NULL;

CREATE FUNCTION hisaab.guard_deleted_account() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$ BEGIN
 IF OLD.deleted_at IS NOT NULL THEN
   RAISE SQLSTATE 'PT404' USING MESSAGE='Account has been deleted';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER deleted_account_guard BEFORE UPDATE ON hisaab.accounts
 FOR EACH ROW EXECUTE FUNCTION hisaab.guard_deleted_account();

CREATE FUNCTION hisaab.account_deletion_preview(p_owner uuid,p_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 WITH payload AS (
 SELECT jsonb_build_object(
   'account',jsonb_build_object('id',a.id,'name',a.name,'version',a.version),
   'entries',coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.id)
     FROM hisaab_api.entries e WHERE e.account_id=a.id),'[]'::jsonb),
   'decisions',coalesce((SELECT jsonb_agg(to_jsonb(d) ORDER BY d.entry_id)
     FROM hisaab.entry_decisions d WHERE d.owner_id=p_owner AND d.account_id=a.id),'[]'::jsonb)
 ) AS value FROM hisaab.accounts a WHERE a.owner_id=p_owner AND a.id=p_id AND a.deleted_at IS NULL
 ) SELECT (value-'decisions') || jsonb_build_object('token',
   encode(sha256(convert_to(value::text,'UTF8')),'hex')) FROM payload
$$;

CREATE FUNCTION hisaab_api.preview_account_deletion(p_id uuid,p_expected_owner uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); preview jsonb;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 preview:=hisaab.account_deletion_preview(owner,p_id);
 IF preview IS NULL THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Account is unavailable'; END IF;
 RETURN preview;
END $$;

CREATE FUNCTION hisaab_api.delete_account(p_id uuid,p_expected_token text,p_expected_owner uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner uuid:=hisaab.current_owner_id(); preview jsonb; previous hisaab.entry_decisions;
 saved hisaab.entry_decisions; note text; affected integer:=0;
BEGIN
 IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
 IF p_expected_owner IS DISTINCT FROM owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed'; END IF;
 -- Match the statement-before-account lock order used by assignment and funding writes.
 PERFORM 1 FROM hisaab.statements WHERE owner_id=owner ORDER BY id FOR UPDATE;
 PERFORM 1 FROM hisaab.accounts WHERE owner_id=owner AND id=p_id AND deleted_at IS NULL FOR UPDATE;
 IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Account is unavailable'; END IF;
 preview:=hisaab.account_deletion_preview(owner,p_id);
 IF p_expected_token IS DISTINCT FROM preview->>'token' THEN
   RAISE SQLSTATE 'PT409' USING MESSAGE='Affected transactions changed; review a fresh preview before deleting';
 END IF;
 note:='Account deleted: '||(preview->'account'->>'name');
 FOR previous IN SELECT * FROM hisaab.entry_decisions WHERE owner_id=owner AND account_id=p_id ORDER BY entry_id FOR UPDATE LOOP
   UPDATE hisaab.entry_decisions SET account_id=NULL,version=version+1,updated_at=CURRENT_TIMESTAMP,reason=note
     WHERE id=previous.id RETURNING * INTO saved;
   INSERT INTO hisaab.decision_events(id,owner_id,entry_id,version,actor_auth_user_id,"before","after",reason)
     VALUES(gen_random_uuid(),owner,saved.entry_id,saved.version,
       (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid,
       to_jsonb(previous),to_jsonb(saved),note);
   INSERT INTO hisaab.assignment_examples(id,owner_id,source_key,merchant_key,direction,kind,is_manual,entry_id,observed_at)
     SELECT gen_random_uuid(),owner,'manual:'||saved.entry_id,
       hisaab.merchant_key(hisaab.effective_values(e,saved)->>'description'),
       coalesce(hisaab.effective_values(e,saved)->>'direction','unknown'),'account',true,saved.entry_id,clock_timestamp()
     FROM hisaab.entries e WHERE e.id=saved.entry_id AND e.owner_id=owner
     ON CONFLICT(owner_id,source_key,kind) DO UPDATE SET account_id=NULL,observed_at=excluded.observed_at;
   affected:=affected+1;
 END LOOP;
 -- Explicit empty manual examples prevent automatic assignment from undoing deletion.
 UPDATE hisaab.assignment_examples SET account_id=NULL,observed_at=clock_timestamp()
   WHERE owner_id=owner AND kind='account' AND account_id=p_id;
 UPDATE hisaab.accounts SET deleted_at=clock_timestamp(),is_archived=true,version=version+1
   WHERE id=p_id AND owner_id=owner;
 RETURN jsonb_build_object('id',p_id,'unassigned_count',affected);
END $$;

REVOKE ALL ON FUNCTION hisaab.guard_deleted_account(),hisaab.account_deletion_preview(uuid,uuid),
 hisaab_api.preview_account_deletion(uuid,uuid),hisaab_api.delete_account(uuid,text,uuid) FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
   GRANT EXECUTE ON FUNCTION hisaab_api.preview_account_deletion(uuid,uuid),hisaab_api.delete_account(uuid,text,uuid) TO authenticated;
 END IF;
END $$;
NOTIFY pgrst,'reload schema';
