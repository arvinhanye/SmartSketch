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

    def test_model_options_keep_id_and_name(self):
        """展示名与实际调用 ID 分开：保存与调用必须用 id。"""
        options = api_settings.extract_model_options({
            "data": [
                {"id": "deepseek-flash", "name": "DeepSeek-V4.1-Flash"},
                {"id": "deepseek-flash", "name": "重复项应被去掉"},
                {"id": "deepseek-pro"},
                {"name": "只有名称时退化为 id"},
                {"id": "   "},
            ],
        })
        self.assertEqual([option["id"] for option in options], ["deepseek-flash", "deepseek-pro", "只有名称时退化为 id"])
        self.assertEqual(options[0]["name"], "DeepSeek-V4.1-Flash")
        self.assertEqual(options[1]["name"], "")

    def test_model_options_accept_plain_strings_and_wrapped_models(self):
        self.assertEqual(api_settings.extract_model_options(["a", "b", "a"]), [{"id": "a", "name": ""}, {"id": "b", "name": ""}])
        self.assertEqual(api_settings.extract_model_options({"data": {"models": [{"id": "x"}]}}), [{"id": "x", "name": ""}])

    def test_model_discovery_returns_options_and_keeps_legacy_field(self):
        body = {"data": [{"id": "chat", "name": "Chat"}, {"id": "text-embedding-v4", "name": "Embedding v4"}]}
        with patch.object(api_settings, "urlopen", return_value=FakeResponse(body)):
            result = api_settings.list_models("embedding", {"EMBEDDING_BASE_URL": "http://127.0.0.1:11434"})
        self.assertTrue(result["ok"])
        # 兼容字段仍在，前端优先用 model_options
        self.assertEqual(result["models"], ["text-embedding-v4", "chat"])
        self.assertEqual(result["model_options"][0], {"id": "text-embedding-v4", "name": "Embedding v4"})
        self.assertEqual(result["count"], 2)

    def test_model_discovery_count_and_latency(self):
        with patch.object(api_settings, "urlopen", return_value=FakeResponse({"data": [{"id": "text-embedding-v4"}]})):
            result = api_settings.list_models("embedding", {"EMBEDDING_BASE_URL": "http://127.0.0.1:11434"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertIsInstance(result["latency_ms"], (int, float))

    def test_model_discovery_accepts_request_list_path(self):
        cases = (
            ("llm", "LLM_BASE_URL", "/models", "http://127.0.0.1:11434/v1/models"),
            ("embedding", "EMBEDDING_BASE_URL", "/custom/models", "http://127.0.0.1:11434/v1/custom/models"),
        )
        for kind, base_field, list_path, expected_url in cases:
            with self.subTest(kind=kind):
                def provider_response(request, timeout):
                    self.assertEqual(request.full_url, expected_url)
                    return FakeResponse({"data": [{"id": "available-model", "name": "Available Model"}]})

                with patch.object(api_settings, "urlopen", side_effect=provider_response):
                    result = api_settings.list_models(kind, {
                        "kind": kind, base_field: "http://127.0.0.1:11434/v1", "list_path": list_path,
                    })
                self.assertTrue(result["ok"], result["error"])
                self.assertEqual(result["model_options"], [{"id": "available-model", "name": "Available Model"}])

    def test_list_path_is_not_a_persisted_config_field(self):
        with self.assertRaises(ValueError):
            save_config({"list_path": "/models"})

    def test_chat_and_extraction_share_one_model(self):
        """大模型只填一处，保存后聊天与知识抽取两个字段一致；留空不清空。"""
        import json
        # 旧配置只写了知识抽取模型：读到的聊天模型也是它（界面不会因此改动旧配置）
        (Path(self.folder.name) / "config.json").write_text(
            json.dumps({"LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_EXTRACTION_MODEL": "legacy-model"}), encoding="utf-8")
        self.assertEqual([public_config()[name] for name in ("LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL")], ["legacy-model", "legacy-model"])

        save_config({"LLM_CHAT_MODEL": "deepseek-flash"})
        values = read_config()
        self.assertEqual([values["LLM_CHAT_MODEL"], values["LLM_EXTRACTION_MODEL"]], ["deepseek-flash", "deepseek-flash"])

        save_config({"LLM_CHAT_MODEL": ""})
        self.assertEqual(read_config()["LLM_CHAT_MODEL"], "deepseek-flash")

    def test_public_config_falls_back_to_extraction_model(self):
        """旧配置只写了知识抽取模型时，界面读到的聊天模型回落到它。"""
        save_config({"LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_EXTRACTION_MODEL": "legacy-model"})
        values = public_config()
        self.assertEqual([values["LLM_CHAT_MODEL"], values["LLM_EXTRACTION_MODEL"]], ["legacy-model", "legacy-model"])

    def test_embedding_migration_guard_keeps_runtime_space(self):
        """保留演示向量时，页面不得切换向量空间。"""
        class Settings:
            EMBEDDING_MODE = "demo"
            EMBEDDING_MODEL = ""
            EMBEDDING_BASE_URL = ""
        with self.assertRaises(ValueError):
            api_settings.save_for_active_space(
                {"EMBEDDING_MODE": "online", "EMBEDDING_MODEL": "text-embedding-v4",
                 "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k"},
                Settings(),
            )
        # 同一向量空间下只改地址以外的内容（如大模型）仍然允许
        api_settings.save_for_active_space({"LLM_CHAT_MODEL": "deepseek-flash", "LLM_MODE": "demo"}, Settings())
        self.assertEqual(read_config()["LLM_CHAT_MODEL"], "deepseek-flash")

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
