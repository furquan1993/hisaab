"""Optimistic, owner-checked assignment writes and audit read models.

https://postgrest.org/en/stable/references/errors.html
https://www.postgresql.org/docs/17/sql-createfunction.html
"""

from alembic import op

revision = "0006_assignment_api"
down_revision = "0005_entry_decisions"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION hisaab.logical_entry_id(p_id uuid) RETURNS uuid
        LANGUAGE sql IMMUTABLE SET search_path='' AS $$ SELECT p_id $$;
        REVOKE ALL ON FUNCTION hisaab.logical_entry_id(uuid) FROM PUBLIC;
        CREATE FUNCTION hisaab_api.save_entry_decision(p_entry_id uuid,p_expected_version integer,p_patch jsonb)
        RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
        AS $$
        DECLARE owner uuid:=hisaab.current_owner_id(); source hisaab.entries;
            previous hisaab.entry_decisions; saved hisaab.entry_decisions;
            root uuid; category uuid; account uuid; active uuid; note text;
        BEGIN
            IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
            IF p_expected_version IS NULL OR p_expected_version<0 OR p_patch IS NULL OR jsonb_typeof(p_patch)<>'object' OR
               EXISTS(SELECT 1 FROM jsonb_object_keys(p_patch) k WHERE k NOT IN ('category_id','account_id','reason')) THEN
                RAISE SQLSTATE 'PT422' USING MESSAGE='Invalid assignment fields';
            END IF;
            SELECT e.* INTO source FROM hisaab.entries e
              JOIN hisaab.imports i ON i.id=e.import_id AND i.owner_id=e.owner_id
              JOIN hisaab.statements s ON s.id=i.statement_id AND s.owner_id=i.owner_id
              WHERE e.id=p_entry_id AND e.owner_id=owner FOR UPDATE OF s;
            IF NOT FOUND THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Entry is unavailable'; END IF;
            SELECT s.active_import_id INTO active FROM hisaab.statements s JOIN hisaab.imports i ON i.statement_id=s.id AND i.owner_id=s.owner_id WHERE i.id=source.import_id;
            IF active IS DISTINCT FROM source.import_id THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Source changed; reload before editing'; END IF;
            root:=hisaab.logical_entry_id(source.id);
            SELECT * INTO previous FROM hisaab.entry_decisions WHERE owner_id=owner AND entry_id=root FOR UPDATE;
            IF coalesce(previous.version,0)<>p_expected_version THEN
                RAISE SQLSTATE 'PT409' USING MESSAGE='Entry changed; reload before saving';
            END IF;
            category:=CASE WHEN p_patch ? 'category_id' THEN (p_patch->>'category_id')::uuid ELSE previous.category_id END;
            account:=CASE WHEN p_patch ? 'account_id' THEN (p_patch->>'account_id')::uuid ELSE previous.account_id END;
            note:=coalesce(p_patch->>'reason','');
            IF length(note)>2000 THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Reason is too long'; END IF;
            IF category IS NOT NULL THEN
                PERFORM 1 FROM hisaab.categories WHERE id=category AND owner_id=owner AND
                  (NOT is_archived OR category IS NOT DISTINCT FROM previous.category_id) FOR SHARE;
                IF NOT FOUND THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose an available category'; END IF;
            END IF;
            IF account IS NOT NULL THEN
                PERFORM 1 FROM hisaab.accounts WHERE id=account AND owner_id=owner AND
                  (NOT is_archived OR account IS NOT DISTINCT FROM previous.account_id) FOR SHARE;
                IF NOT FOUND THEN RAISE SQLSTATE 'PT422' USING MESSAGE='Choose an available account'; END IF;
            END IF;
            INSERT INTO hisaab.entry_decisions(id,owner_id,entry_id,category_id,account_id,version,reason)
              VALUES(gen_random_uuid(),owner,root,category,account,p_expected_version+1,note)
              ON CONFLICT(owner_id,entry_id) DO UPDATE SET category_id=excluded.category_id,
                account_id=excluded.account_id,version=excluded.version,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP
              RETURNING * INTO saved;
            INSERT INTO hisaab.decision_events(id,owner_id,entry_id,version,actor_auth_user_id,"before","after",reason)
              VALUES(gen_random_uuid(),owner,root,saved.version,
                (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid,
                coalesce(to_jsonb(previous),'{}'::jsonb),to_jsonb(saved),note);
            RETURN to_jsonb(saved)-'owner_id';
        EXCEPTION WHEN invalid_text_representation THEN
            RAISE SQLSTATE 'PT422' USING MESSAGE='Choose valid label identifiers';
        END $$;
        REVOKE ALL ON FUNCTION hisaab_api.save_entry_decision(uuid,integer,jsonb) FROM PUBLIC;
        ALTER VIEW hisaab_api.entries RENAME TO extracted_entries;
        ALTER VIEW hisaab_api.extracted_entries SET SCHEMA hisaab;
        CREATE VIEW hisaab_api.entries WITH (security_invoker=true) AS
          SELECT e.*,hisaab.logical_entry_id(e.id) AS logical_entry_id,
            coalesce(d.version,0) AS decision_version,d.category_id,c.name AS category_name,
            d.account_id,a.name AS account_name,coalesce(d.overrides::jsonb,'{}'::jsonb) AS overrides,
            coalesce(d.acknowledged::jsonb,'[]'::jsonb) AS acknowledged,d.source_fingerprint,
            d.updated_at AS decision_updated_at
          FROM hisaab.extracted_entries e
          LEFT JOIN hisaab.entry_decisions d ON d.entry_id=hisaab.logical_entry_id(e.id) AND d.owner_id=hisaab.current_owner_id()
          LEFT JOIN hisaab.categories c ON c.id=d.category_id AND c.owner_id=d.owner_id
          LEFT JOIN hisaab.accounts a ON a.id=d.account_id AND a.owner_id=d.owner_id;
        CREATE VIEW hisaab_api.decision_history WITH (security_invoker=true) AS
          SELECT id,entry_id,version,actor_auth_user_id,"before","after",reason,created_at
          FROM hisaab.decision_events;
        REVOKE ALL ON hisaab_api.entries,hisaab_api.decision_history FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON hisaab_api.entries,hisaab_api.decision_history FROM anon;
            REVOKE ALL ON FUNCTION hisaab.logical_entry_id(uuid),hisaab_api.save_entry_decision(uuid,integer,jsonb) FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON hisaab_api.entries,hisaab_api.decision_history FROM authenticated;
            GRANT SELECT ON hisaab_api.entries,hisaab_api.decision_history TO authenticated;
            GRANT EXECUTE ON FUNCTION hisaab.logical_entry_id(uuid),hisaab_api.save_entry_decision(uuid,integer,jsonb) TO authenticated;
          END IF;
        END $$;
        NOTIFY pgrst,'reload schema';
    """)


def downgrade():
    op.execute("""
        DROP VIEW hisaab_api.decision_history;
        DROP VIEW hisaab_api.entries;
        ALTER VIEW hisaab.extracted_entries SET SCHEMA hisaab_api;
        ALTER VIEW hisaab_api.extracted_entries RENAME TO entries;
        DROP FUNCTION hisaab_api.save_entry_decision(uuid,integer,jsonb);
        DROP FUNCTION hisaab.logical_entry_id(uuid);
    """)
