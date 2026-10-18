"""Optional Auth identity and deny-by-default read policies.

Identity is not an auth.users FK: app backups remain provider-independent.
PostgREST validates JWTs before setting request.jwt.claims:
https://postgrest.org/en/stable/references/transactions.html#transaction-scoped-settings
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_browser_identity"
down_revision = "0001_initial_schema"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "owners", sa.Column("auth_user_id", sa.Uuid(), nullable=True), schema="hisaab"
    )
    op.create_unique_constraint(
        "uq_owners_auth_user_id", "owners", ["auth_user_id"], schema="hisaab"
    )
    # Narrow definer helper avoids recursive owners RLS. No arbitrary owner argument.
    # https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY
    op.execute("""
        CREATE FUNCTION hisaab.current_owner_id() RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT id FROM hisaab.owners
            WHERE auth_user_id::text =
                (NULLIF(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
            AND (NULLIF(pg_catalog.current_setting('request.jwt.claims', true), '')::jsonb ->> 'role') = 'authenticated'
        $$;
        REVOKE ALL ON FUNCTION hisaab.current_owner_id() FROM PUBLIC;
    """)
    for table in ("owners", "cards", "statements", "imports", "entries"):
        column = "id" if table == "owners" else "owner_id"
        op.execute(f"""
            CREATE POLICY browser_read ON hisaab.{table} FOR SELECT
            USING ({column} = (SELECT hisaab.current_owner_id()))
        """)
    op.execute("CREATE SCHEMA hisaab_api; REVOKE ALL ON SCHEMA hisaab_api FROM PUBLIC")
    # Override platform defaults: no browser write or raw-PDF privileges.
    op.execute("""
        REVOKE ALL ON public.hisaab_schema_version FROM PUBLIC;
        ALTER DEFAULT PRIVILEGES IN SCHEMA hisaab, hisaab_api
            REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
        DO $$ DECLARE browser_role text;
        BEGIN
            FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=browser_role) THEN
                    EXECUTE format('REVOKE ALL ON public.hisaab_schema_version FROM %I', browser_role);
                    EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hisaab, hisaab_api FROM %I', browser_role);
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA hisaab, hisaab_api FROM %I', browser_role);
                    EXECUTE format('REVOKE ALL ON SCHEMA hisaab, hisaab_api FROM %I', browser_role);
                END IF;
            END LOOP;
        END $$;
    """)
    # Invoker views obey the caller's RLS, not the privileged view creator.
    # https://supabase.com/docs/guides/database/postgres/row-level-security#views
    op.execute("""
        CREATE VIEW hisaab_api.profile WITH (security_invoker = true) AS
        SELECT id, display_name FROM hisaab.owners;
        REVOKE ALL ON hisaab_api.profile FROM PUBLIC;
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                REVOKE ALL ON hisaab_api.profile FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                REVOKE ALL ON hisaab_api.profile FROM authenticated;
                GRANT USAGE ON SCHEMA hisaab, hisaab_api TO authenticated;
                GRANT EXECUTE ON FUNCTION hisaab.current_owner_id() TO authenticated;
                GRANT SELECT (id, display_name) ON hisaab.owners TO authenticated;
                GRANT SELECT ON hisaab_api.profile TO authenticated;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("DROP VIEW hisaab_api.profile; DROP SCHEMA hisaab_api")
    for table in ("owners", "cards", "statements", "imports", "entries"):
        op.execute(f"DROP POLICY browser_read ON hisaab.{table}")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE SELECT (id, display_name) ON hisaab.owners FROM authenticated;
            REVOKE USAGE ON SCHEMA hisaab FROM authenticated;
          END IF;
        END $$;
        DROP FUNCTION hisaab.current_owner_id()
    """)
    op.drop_constraint("uq_owners_auth_user_id", "owners", schema="hisaab")
    op.drop_column("owners", "auth_user_id", schema="hisaab")
