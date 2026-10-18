"""Private local settings, using Python 3.11's standard TOML reader."""

import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import URL

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.local.toml"


class ConfigurationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DatabaseConfig:
    url: str | URL = field(repr=False)
    connect_timeout_seconds: int = 10


def _database_url(database: dict) -> str | URL:
    raw_url = database.get("url", "")
    if not isinstance(raw_url, str):
        raise ConfigurationError("config_invalid", "Database url must be a string.")
    fields = ("host", "database", "user", "pass")
    if raw_url.strip():
        if any(key in database for key in (*fields, "port", "sslmode")):
            raise ConfigurationError(
                "config_invalid",
                "Choose either a database URL or separate connection fields.",
            )
        return raw_url.strip()
    if not all(
        isinstance(database.get(key), str) and database[key].strip() for key in fields
    ):
        raise ConfigurationError(
            "config_incomplete",
            "Set a database URL or host, database, user, and pass fields.",
        )
    port = database.get("port", 5432)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ConfigurationError(
            "config_invalid", "Database port must be an integer from 1 to 65535."
        )
    sslmode = database.get("sslmode", "require")
    if sslmode not in ("require", "verify-ca", "verify-full"):
        raise ConfigurationError(
            "config_invalid", "PostgreSQL connections must require TLS."
        )
    # URL.create accepts literal passwords without manual URL encoding.
    # https://docs.sqlalchemy.org/en/21/core/engines.html#creating-urls-programmatically
    return URL.create(
        "postgresql+psycopg",
        host=database["host"],
        port=port,
        database=database["database"],
        username=database["user"],
        password=database["pass"],
        query={"sslmode": sslmode},
    )


def _read_config(path: str | Path) -> dict:
    """Never put configuration contents or parser exceptions in public errors."""
    path = Path(path)
    try:
        with path.open("rb") as source:
            if (
                os.name == "posix"
                and stat.S_IMODE(os.fstat(source.fileno()).st_mode) & 0o077
            ):
                raise ConfigurationError(
                    "config_permissions",
                    "Make the database configuration owner-only (mode 0600).",
                )
            payload = tomllib.load(source)
    except FileNotFoundError:
        raise ConfigurationError(
            "config_missing",
            "Create a private config.local.toml from config.example.toml.",
        ) from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise ConfigurationError(
            "config_invalid", "Database configuration must be valid TOML."
        ) from None
    except OSError:
        raise ConfigurationError(
            "config_unreadable", "Cannot read the private database configuration."
        ) from None
    return payload


def load_config(path: str | Path = DEFAULT_CONFIG) -> DatabaseConfig:
    payload = _read_config(path)
    database = payload.get("database")
    if not isinstance(database, dict):
        raise ConfigurationError(
            "config_invalid", "Set a database section in the configuration."
        )
    timeout = database.get("connect_timeout_seconds", 10)
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ConfigurationError(
            "config_invalid",
            "Database connect_timeout_seconds must be an integer from 1 to 60.",
        )
    return DatabaseConfig(_database_url(database), timeout)


@dataclass(frozen=True)
class RetentionConfig:
    pdf_months: int = 24
    pdf_cleanup_enabled: bool = False


def load_retention_config(path: str | Path = DEFAULT_CONFIG) -> RetentionConfig:
    """Read policy only; this does not run cleanup or delete any data."""
    retention = _read_config(path).get("retention", {})
    if not isinstance(retention, dict) or set(retention) - {
        "pdf_months",
        "pdf_cleanup_enabled",
    }:
        raise ConfigurationError(
            "config_invalid", "Invalid retention configuration keys."
        )
    months = retention.get("pdf_months", 24)
    enabled = retention.get("pdf_cleanup_enabled", False)
    if type(months) is not int or months <= 0 or type(enabled) is not bool:
        raise ConfigurationError(
            "config_invalid",
            "Retention requires positive integer pdf_months and boolean pdf_cleanup_enabled.",
        )
    return RetentionConfig(months, enabled)
