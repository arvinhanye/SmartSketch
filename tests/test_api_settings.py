import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.api_settings import read_config, save_config, public_config


class ApiSettingsTests(unittest.TestCase):
    def test_preserves_secrets_without_returning_them(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SMARTSKETCH_API_CONFIG": str(Path(folder) / "config.json")}):
            save_config({"LLM_API_KEY": "test-secret", "LLM_BASE_URL": "https://api.deepseek.com/v1"})
            save_config({"LLM_CHAT_MODEL": "deepseek-chat"})
            self.assertEqual(read_config()["LLM_API_KEY"], "test-secret")
            self.assertNotIn("test-secret", str(public_config()))
            if os.name == "nt":
                self.assertNotIn("test-secret", (Path(folder) / "config.json").read_text())

    def test_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            save_config({"LLM_BASE_URL": "file:///private"})


if __name__ == "__main__":
    unittest.main()
