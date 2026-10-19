"""In-memory Supabase password session; no database credentials or token files.

Password grant: https://github.com/supabase/auth#post-token
RPCs: https://docs.postgrest.org/en/stable/references/api/functions.html
"""

import base64
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from core.config import CONFIG_ROOT
from core.persistence.store import StoreError

PUBLIC_CONFIG = CONFIG_ROOT / "supabase.public.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward passwords, tokens or PDFs to a redirected destination.
        return None


def public_config(path=PUBLIC_CONFIG):
    try:
        data = json.loads(Path(path).read_text())
        url, key = data["url"], data["publishable_key"]
        parsed = urlsplit(url)
        local = parsed.hostname in ("localhost", "127.0.0.1")
        if (parsed.scheme != "https" and not (local and parsed.scheme == "http")) or (
            not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in ("", "/")
        ):
            raise ValueError
        if not isinstance(key, str):
            raise ValueError
        # Support the legacy public anon key for the disposable Supabase stack.
        if not key.startswith("sb_publishable_"):
            claims = key.split(".")[1]
            if json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["role"] != "anon":
                raise ValueError
        return url.rstrip("/"), key
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise StoreError("public_config_invalid", "Use a project-root HTTPS URL and a public publishable/anon key in supabase.public.json.") from None


class UserAPI:
    def __init__(self, url, key):
        self.url, self.key = url, key
        self.access_token = self.refresh_token = None
        self.expires_at = 0
        self.opener = build_opener(NoRedirect())

    def _request(self, path, data=None, *, auth=False, method=None):
        headers = {"apikey": self.key, "Accept": "application/json"}
        if not auth:
            if not self.access_token:
                raise StoreError("sign_in_required", "Sign in before importing.")
            headers["Authorization"] = "Bearer " + self.access_token
            headers["Accept-Profile"] = headers["Content-Profile"] = "hisaab_api"
        if data is not None:
            headers["Content-Type"] = "application/json"
        body = None if data is None else json.dumps(data, allow_nan=False).encode()
        request = Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise ValueError
                return json.loads(raw) if raw else None
        except HTTPError as error:
            try:
                code = json.loads(error.read(8192)).get("code")
            except (ValueError, AttributeError):
                code = None
            if auth:
                raise StoreError("sign_in_failed", "Sign-in failed or expired. Check your UI email/password and project availability, then run the command again.") from None
            if code == "PGRST202":
                raise StoreError("import_api_unavailable", "The authenticated import API is unavailable. Ask the operator to deploy migration 0020_authenticated_imports.") from None
            errors = {
                401: ("session_expired", "Your session expired. Run the command again to sign in; retrying the same PDF is safe."),
                403: ("access_denied", "This account is not authorized. Confirm your linked profile with the workspace operator."),
                404: ("card_not_found", "The card is unavailable for your signed-in account. Check Cards in the UI."),
                409: ("import_conflict", "The card or statement changed. Reload the UI and retry the same PDF."),
                422: ("invalid_import", "The PDF extraction was rejected. Check the card bank, PDF and parser version; no import was committed."),
            }
            error_code, message = errors.get(error.code, ("api_request_failed", "Could not confirm the request. Check connectivity and retry the same PDF; duplicates are safe."))
            raise StoreError(error_code, message) from None
        except (URLError, OSError, ValueError):
            raise StoreError("api_request_failed", "Could not confirm the request. Check connectivity and retry the same PDF; duplicates are safe.") from None

    def _session(self, response):
        try:
            token, refresh = response["access_token"], response["refresh_token"]
            expires = response["expires_in"]
            if not isinstance(token, str) or not token or not isinstance(refresh, str) or not refresh:
                raise ValueError
            if type(expires) is not int or not 0 < expires <= 604800:
                raise ValueError
        except (TypeError, KeyError, ValueError):
            raise StoreError("invalid_auth_response", "Could not establish a valid sign-in session. Try again.") from None
        self.access_token, self.refresh_token = token, refresh
        self.expires_at = time.time() + expires

    def sign_in(self, email, password):
        self._session(self._request("/auth/v1/token?grant_type=password",
                                  {"email": email, "password": password}, auth=True))

    def request(self, path, data=None):
        if self.refresh_token and time.time() + 60 >= self.expires_at:
            self._session(self._request("/auth/v1/token?grant_type=refresh_token",
                                      {"refresh_token": self.refresh_token}, auth=True))
        return self._request("/rest/v1" + path, data)

    def close(self):
        try:
            if self.access_token:
                self._request("/auth/v1/logout?scope=local", method="POST")
        except StoreError:
            pass
        finally:
            self.access_token = self.refresh_token = None
            self.expires_at = 0
