"""Owner-scoped independent Categories and funding Accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0004_labels"
down_revision = "0003_browser_queries"
branch_labels = depends_on = None


def upgrade():
    for name in ("categories", "accounts"):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "owner_id",
                sa.Uuid(),
                sa.ForeignKey("hisaab.owners.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column(
                "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
            ),
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
            sa.UniqueConstraint("owner_id", "id", name=f"uq_{name}_owner_id"),
            sa.UniqueConstraint("owner_id", "name", name=f"uq_{name}_name"),
            sa.CheckConstraint(
                "length(btrim(name)) BETWEEN 1 AND 120", name=f"ck_{name}_name"
            ),
            sa.CheckConstraint("version > 0", name=f"ck_{name}_version"),
            schema="hisaab",
        )
        op.execute(f"ALTER TABLE hisaab.{name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY browser_read ON hisaab.{name} FOR SELECT USING (owner_id=(SELECT hisaab.current_owner_id()))"
        )
    op.execute("""
        CREATE VIEW hisaab_api.labels WITH (security_invoker=true) AS
        SELECT id,'category'::text AS kind,name,is_archived,version FROM hisaab.categories
        UNION ALL SELECT id,'account',name,is_archived,version FROM hisaab.accounts;
        REVOKE ALL ON hisaab_api.labels FROM PUBLIC;
        CREATE FUNCTION hisaab_api.save_label(
            p_kind text,p_name text,p_id uuid DEFAULT NULL,
            p_expected_version integer DEFAULT 0,p_archived boolean DEFAULT false,p_expected_owner uuid DEFAULT NULL
        ) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=''
        AS $$
        DECLARE owner uuid:=hisaab.current_owner_id(); target text;
                saved jsonb; current_version integer; duplicate_name boolean;
        BEGIN
            IF owner IS NULL THEN RAISE SQLSTATE '42501' USING MESSAGE='Owner is not configured'; END IF;
            IF p_expected_owner IS NOT NULL AND p_expected_owner<>owner THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Signed-in owner changed; reload before saving'; END IF;
            IF p_kind NOT IN ('category','account') OR p_kind IS NULL OR
               p_name IS NULL OR length(btrim(p_name)) NOT BETWEEN 1 AND 120 OR
               p_name ~ '[[:cntrl:]]' OR p_archived IS NULL OR p_expected_version IS NULL OR p_expected_version<0 THEN
                RAISE SQLSTATE 'PT422' USING MESSAGE='Use a valid label kind and a name of 1 to 120 characters';
            END IF;
            target:=CASE p_kind WHEN 'category' THEN 'categories' ELSE 'accounts' END;
            PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(owner::text||':'||target,0));
            IF p_id IS NULL THEN
                IF p_expected_version<>0 THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Reload labels before saving'; END IF;
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM hisaab.%I WHERE owner_id=$1 AND lower(name)=lower($2))',target)
                    INTO duplicate_name USING owner,btrim(p_name);
                IF duplicate_name THEN
                    RAISE SQLSTATE 'PT409' USING MESSAGE='This label name already exists';
                END IF;
                EXECUTE format('INSERT INTO hisaab.%I (id,owner_id,name,is_archived) VALUES (gen_random_uuid(),$1,$2,$3) RETURNING to_jsonb(%I.*)',target,target)
                    INTO saved USING owner,btrim(p_name),p_archived;
            ELSE
                EXECUTE format('SELECT version FROM hisaab.%I WHERE id=$1 AND owner_id=$2 FOR UPDATE',target)
                    INTO current_version USING p_id,owner;
                IF current_version IS NULL THEN RAISE SQLSTATE 'PT404' USING MESSAGE='Label is unavailable'; END IF;
                IF current_version<>p_expected_version THEN RAISE SQLSTATE 'PT409' USING MESSAGE='Label changed; reload before saving'; END IF;
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM hisaab.%I WHERE owner_id=$1 AND id<>$2 AND lower(name)=lower($3))',target)
                    INTO duplicate_name USING owner,p_id,btrim(p_name);
                IF duplicate_name THEN
                    RAISE SQLSTATE 'PT409' USING MESSAGE='This label name already exists';
                END IF;
                EXECUTE format('UPDATE hisaab.%I SET name=$1,is_archived=$2,version=version+1 WHERE id=$3 AND owner_id=$4 RETURNING to_jsonb(%I.*)',target,target)
                    INTO saved USING btrim(p_name),p_archived,p_id,owner;
            END IF;
            RETURN (saved-'owner_id'-'created_at')||jsonb_build_object('kind',p_kind);
        END $$;
        REVOKE ALL ON FUNCTION hisaab_api.save_label(text,text,uuid,integer,boolean,uuid) FROM PUBLIC;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                REVOKE ALL ON hisaab.categories,hisaab.accounts,hisaab_api.labels FROM anon;
                REVOKE ALL ON FUNCTION hisaab_api.save_label(text,text,uuid,integer,boolean,uuid) FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE ALL ON hisaab.categories,hisaab.accounts,hisaab_api.labels FROM authenticated;
                GRANT SELECT ON hisaab.categories,hisaab.accounts,hisaab_api.labels TO authenticated;
                GRANT EXECUTE ON FUNCTION hisaab_api.save_label(text,text,uuid,integer,boolean,uuid) TO authenticated;
            END IF;
        END $$;
        NOTIFY pgrst,'reload schema';
    """)


def downgrade():
    op.execute(
        "DROP FUNCTION IF EXISTS hisaab_api.save_label(text,text,uuid,integer,boolean,uuid); DROP FUNCTION IF EXISTS hisaab_api.save_label(text,text,uuid,integer,boolean); DROP VIEW hisaab_api.labels"
    )
    op.drop_table("accounts", schema="hisaab")
    op.drop_table("categories", schema="hisaab")
