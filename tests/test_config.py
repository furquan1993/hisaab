import os
import tempfile
import unittest
from pathlib import Path

from core.config import ConfigurationError, load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.local.toml"

    def configure(self, content):
        self.path.write_text(content)
        self.path.chmod(0o600)

    def error_code(self, expected):
        with self.assertRaises(ConfigurationError) as error:
            load_config(self.path)
        self.assertEqual(error.exception.code, expected)
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_loads_private_toml_without_exposing_url_in_repr(self):
        self.configure(
            "[database]\nurl = 'postgresql://user:synthetic-secret@localhost/test'\n"
        )
        config = load_config(self.path)
        self.assertIn("synthetic-secret", config.url)
        self.assertNotIn("synthetic-secret", repr(config))
        self.assertEqual(config.connect_timeout_seconds, 10)

    def test_separate_fields_accept_raw_password_special_characters(self):
        self.configure(
            "[database]\nurl = ''\nhost = 'localhost'\nport = 5432\n"
            "database = 'example'\nuser = 'example'\npass = 'synthetic-secret@:/?#'\n"
        )
        config = load_config(self.path)
        self.assertEqual(config.url.drivername, "postgresql+psycopg")
        self.assertEqual(config.url.host, "localhost")
        self.assertEqual(config.url.database, "example")
        self.assertEqual(config.url.username, "example")
        self.assertEqual(config.url.password, "synthetic-secret@:/?#")
        self.assertEqual(config.url.query["sslmode"], "require")
        self.assertNotIn("synthetic-secret", repr(config))

    def test_separate_fields_default_port(self):
        self.configure(
            "[database]\nhost = 'localhost'\ndatabase = 'example'\n"
            "user = 'example'\npass = 'synthetic-secret'\n"
        )
        self.assertEqual(load_config(self.path).url.port, 5432)

    def test_separate_fields_reject_invalid_ports(self):
        for port in ("true", "0", "65536", "'5432'"):
            with self.subTest(port=port):
                self.configure(
                    "[database]\nhost = 'localhost'\ndatabase = 'example'\n"
                    "user = 'example'\npass = 'synthetic-secret'\nport = " + port + "\n"
                )
                self.error_code("config_invalid")

    def test_separate_fields_require_all_credentials(self):
        self.configure("[database]\nhost = 'localhost'\nuser = 'example'\n")
        self.error_code("config_incomplete")

    def test_separate_fields_preserve_stronger_tls(self):
        self.configure(
            "[database]\nhost = 'localhost'\ndatabase = 'example'\n"
            "user = 'example'\npass = 'synthetic-secret'\nsslmode = 'verify-full'\n"
        )
        self.assertEqual(load_config(self.path).url.query["sslmode"], "verify-full")

    def test_mixed_nonempty_url_and_fields_are_rejected(self):
        self.configure("[database]\nurl = 'sqlite:///:memory:'\nhost = 'localhost'\n")
        self.error_code("config_invalid")

    def test_explicit_timeout(self):
        self.configure(
            "[database]\nurl = 'sqlite:///:memory:'\nconnect_timeout_seconds = 5\n"
        )
        self.assertEqual(load_config(self.path).connect_timeout_seconds, 5)

    def test_missing_file(self):
        self.error_code("config_missing")

    def test_empty_url_requires_configuration(self):
        self.configure("[database]\nurl = ''\n")
        self.error_code("config_incomplete")

    def test_bad_toml_does_not_echo_source(self):
        self.configure("[database]\nurl = 'synthetic-secret\n")
        self.error_code("config_invalid")

    def test_invalid_shapes_and_values(self):
        for content in (
            "",
            "[database]\nurl = 12\n",
            "[database]\nurl = 'synthetic-secret'\nconnect_timeout_seconds = true\n",
            "[database]\nurl = 'synthetic-secret'\nconnect_timeout_seconds = 0\n",
            "[database]\nurl = 'synthetic-secret'\nconnect_timeout_seconds = 61\n",
        ):
            with self.subTest(content=content):
                self.configure(content)
                self.error_code("config_invalid")

    def test_invalid_utf8_is_safe(self):
        self.path.write_bytes(b"\xffsynthetic-secret")
        self.path.chmod(0o600)
        self.error_code("config_invalid")

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions")
    def test_rejects_group_or_world_readable_credentials(self):
        self.configure("[database]\nurl = 'synthetic-secret'\n")
        self.path.chmod(0o644)
        self.error_code("config_permissions")
