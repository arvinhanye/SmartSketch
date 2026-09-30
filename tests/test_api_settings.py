import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.api_settings import read_config, save_config, public_config
from app.services import api_settings

class FakeResponse:
    status = 200
    def __init__(self, body):
        import json
        self.body = json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, _limit): return self.body


class ApiSettingsTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parent / '.tmp-api-settings'
        root.mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.folder.cleanup)
        env = patch.dict(os.environ, {"SMARTSKETCH_API_CONFIG": str(Path(self.folder.name) / "config.json")})
        env.start()
        self.addCleanup(env.stop)

    def test_preserves_secrets_without_returning_them(self):
        with patch.dict(os.environ, {"SMARTSKETCH_API_CONFIG": str(Path(self.folder.name) / "config.json")}):
            save_config({"LLM_API_KEY": "test-secret", "LLM_BASE_URL": "https://api.deepseek.com/v1"})
            save_config({"LLM_CHAT_MODEL": "deepseek-chat"})
            self.assertEqual(read_config()["LLM_API_KEY"], "test-secret")
            self.assertNotIn("test-secret", str(public_config()))
            if os.name == "nt":
                self.assertNotIn("test-secret", (Path(self.folder.name) / "config.json").read_text())

    def test_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            save_config({"LLM_BASE_URL": "file:///private"})

    def test_extract_model_ids_shapes(self):
        self.assertEqual(api_settings.extract_model_ids({"data": [{"id": "chat"}, {"id": "chat"}]}), ["chat"])
        self.assertEqual(api_settings.extract_model_ids({"models": [{"name": "embed"}]}), ["embed"])

    def test_model_discovery_count_and_latency(self):
        with patch.object(api_settings, "urlopen", return_value=FakeResponse({"data": [{"id": "chat"}, {"id": "text-embedding"}]})):
            result = api_settings.list_models("embedding", {"EMBEDDING_BASE_URL": "http://127.0.0.1:11434"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertIsInstance(result["latency_ms"], (int, float))

    def test_blank_model_keeps_saved_selection(self):
        save_config({"LLM_CHAT_MODEL": "chosen"})
        save_config({"LLM_CHAT_MODEL": ""})
        self.assertEqual(read_config()["LLM_CHAT_MODEL"], "chosen")

    def test_http_local_only(self):
        save_config({"LLM_BASE_URL": "http://127.0.0.1:11434/v1"})
        with self.assertRaises(ValueError):
            save_config({"LLM_BASE_URL": "http://example.com/v1"})


if __name__ == "__main__":
    unittest.main()
