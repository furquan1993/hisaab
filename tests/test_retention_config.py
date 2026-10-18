import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import ConfigurationError, load_retention_config


class RetentionConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.local.toml"
        scope = patch("core.config.CONFIG_ROOT", self.path.parent.resolve())
        scope.start()
        self.addCleanup(scope.stop)

    def configure(self, content):
        self.path.write_text(content)
        self.path.chmod(0o600)

    def test_defaults_are_configurable_and_cleanup_is_disabled(self):
        self.configure("[database]\nurl = 'sqlite:///:memory:'\n")
        settings = load_retention_config(self.path)
        self.assertEqual(settings.pdf_months, 24)
        self.assertFalse(settings.pdf_cleanup_enabled)

    def test_explicit_retention(self):
        self.configure("[retention]\npdf_months = 60\npdf_cleanup_enabled = true\n")
        settings = load_retention_config(self.path)
        self.assertEqual(settings.pdf_months, 60)
        self.assertTrue(settings.pdf_cleanup_enabled)

    def test_invalid_policy_is_not_silently_ignored(self):
        for content in (
            "retention = 'synthetic-secret'",
            "[retention]\npdf_months = 0",
            "[retention]\npdf_months = -1",
            "[retention]\npdf_months = true",
            "[retention]\npdf_months = '24'",
            "[retention]\npdf_cleanup_enabled = 'false'",
            "[retention]\npdf_moths = 36",
        ):
            with self.subTest(content=content):
                self.configure(content)
                with self.assertRaises(ConfigurationError) as error:
                    load_retention_config(self.path)
                self.assertEqual(error.exception.code, "config_invalid")
                self.assertNotIn("synthetic-secret", str(error.exception))
