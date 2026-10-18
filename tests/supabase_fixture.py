"""Real Auth/JWT/REST tests, strictly limited to the disposable CLI stack.

Never reads config.local.toml, web/.env.local or production credentials.
"""

import json
import os
import secrets
import subprocess
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, delete, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from core.persistence.models import Card, Entry, ImportRecord, Owner, Statement
from tests.persistence_fixture import seed
from tests.postgres_fixture import migration_config


def request(url, *, method="GET", token=None, key=None, data=None, schema=True):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["apikey"] = key
    if schema:
        headers["Accept-Profile"] = "hisaab_api"
        headers["Content-Profile"] = "hisaab_api"
    if data is not None:
        headers["Content-Type"] = "application/json"
    body = None if data is None else json.dumps(data).encode()
    try:
        with urlopen(
            Request(url, data=body, headers=headers, method=method), timeout=15
        ) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else None


@unittest.skipUnless(
    os.environ.get("HISAAB_SUPABASE_TESTS") == "1",
    "Disposable Supabase opt-in required",
)
class SupabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["docker", "inspect", "supabase_db_hisaab-test", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode or result.stdout.strip() != "/supabase_db_hisaab-test":
            raise RuntimeError(
                "Only the local hisaab-test Supabase stack is permitted."
            )
        status = json.loads(Path(os.environ["HISAAB_SUPABASE_STATUS_FILE"]).read_text())
        cls.api = status["API_URL"]
        db = make_url(status["DB_URL"])
        if (
            cls.api != "http://127.0.0.1:54321"
            or db.host != "127.0.0.1"
            or db.port != 54322
        ):
            raise RuntimeError("Refusing a non-disposable Supabase target.")
        cls.anon, cls.admin = status["ANON_KEY"], status["SERVICE_ROLE_KEY"]
        cls.engine = create_engine(
            db.set(drivername="postgresql+psycopg"), hide_parameters=True
        )
        cls.addClassCleanup(cls.engine.dispose)
        with cls.engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
            connection.execute(
                text(
                    "ALTER ROLE authenticator SET pgrst.db_schemas='public,hisaab_api'"
                )
            )
            connection.execute(text("NOTIFY pgrst, 'reload config'"))
            connection.execute(text("NOTIFY pgrst, 'reload schema'"))
        cls.users, cls.tokens, cls.owners, cls.logins = [], [], [], []
        cls.addClassCleanup(cls.cleanup_records)
        cls.records = []
        for index in range(3):
            email = f"hisaab-test-{uuid4().hex}@example.invalid"
            password = secrets.token_urlsafe(24)
            code, user = request(
                cls.api + "/auth/v1/admin/users",
                method="POST",
                token=cls.admin,
                key=cls.admin,
                schema=False,
                data={"email": email, "password": password, "email_confirm": True},
            )
            if code not in (200, 201):
                raise RuntimeError("Synthetic Auth user provisioning failed.")
            cls.users.append(user["id"])
            code, login = request(
                cls.api + "/auth/v1/token?grant_type=password",
                method="POST",
                key=cls.anon,
                schema=False,
                data={"email": email, "password": password},
            )
            if code != 200:
                raise RuntimeError("Synthetic password login failed.")
            cls.tokens.append(login["access_token"])
            cls.logins.append((email, password))
            if index < 2:
                with (
                    Session(cls.engine, expire_on_commit=False) as session,
                    session.begin(),
                ):
                    rows = seed(session)
                    rows.owner.auth_user_id = user["id"]
                    session.flush()
                    cls.owners.append(rows.owner.id)
                    cls.records.append(rows)
        for _ in range(40):
            code, profile = cls.call("/profile", cls.tokens[0])
            if code == 200 and len(profile) == 1:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Disposable Data API readiness check failed.")

    @classmethod
    def call(cls, path, token=None, **options):
        return request(
            cls.api + "/rest/v1" + path, token=token, key=cls.anon, **options
        )

    @classmethod
    def cleanup_records(cls):
        if cls.owners:
            with cls.engine.begin() as connection:
                for name in (
                    "decision_events",
                    "entry_decisions",
                    "import_reviews",
                    "entry_links",
                    "parser_revisions",
                    "categories",
                    "accounts",
                ):
                    if connection.scalar(
                        text("SELECT to_regclass(:name)"), {"name": "hisaab." + name}
                    ):
                        connection.exec_driver_sql(
                            "DELETE FROM hisaab." + name + " WHERE owner_id=ANY(%s)",
                            (cls.owners,),
                        )
                connection.execute(delete(Entry).where(Entry.owner_id.in_(cls.owners)))
                connection.execute(
                    update(Statement)
                    .where(Statement.owner_id.in_(cls.owners))
                    .values(active_import_id=None)
                )
                for model in (ImportRecord, Statement, Card, Owner):
                    column = model.id if model is Owner else model.owner_id
                    connection.execute(delete(model).where(column.in_(cls.owners)))
        for user in cls.users:
            request(
                cls.api + "/auth/v1/admin/users/" + user,
                method="DELETE",
                token=cls.admin,
                key=cls.admin,
                schema=False,
            )
