import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.services.api_settings import read_config, save_config, public_config, target_embedding_space
from app.services import api_settings
from app.services.embedding_models import capability_for, supports_dimension_parameter

class FakeResponse:
    status = 200
    def __init__(self, body):
        self.body = json.dumps(body).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, _limit): return self.body


class FakeEmbeddingResponse(FakeResponse):
    """记录请求体，便于断言实际发出去的 dimensions。"""

    def __init__(self, body, sink):
        super().__init__(body)
        self._sink = sink


class CapabilityTests(unittest.TestCase):
    """能力表只登记已核对官方文档的模型；未登记即未知，不推测维度。"""

    def test_known_model_reports_documented_dimensions(self):
        capability = capability_for("text-embedding-v4")
        self.assertTrue(capability["known"])
        self.assertEqual(capability["default"], 1024)
        self.assertEqual(capability["flexible"], "flexible")
        self.assertIn(1536, capability["dimensions"])
        self.assertIn("alibabacloud.com", capability["source"])

    def test_unknown_model_is_reported_unknown(self):
        capability = capability_for("my-private-embedding")
        self.assertFalse(capability["known"])
        self.assertEqual(capability["dimensions"], [])
        self.assertIsNone(capability["default"])
        self.assertFalse(supports_dimension_parameter("my-private-embedding"))


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

    def test_saving_requires_complete_real_api_config(self):
        """只看真实服务：配置不完整时保存被拒，并提示要填什么。"""
        with self.assertRaises(ValueError) as incomplete:
            api_settings.save_for_active_space({"LLM_BASE_URL": "https://api.deepseek.com/v1"}, Settings())
        self.assertIn("请选择大模型和向量模型", str(incomplete.exception))

        # 配全之后可以保存，并且不再接受演示模式
        api_settings.save_for_active_space({
            "LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_API_KEY": "k", "LLM_CHAT_MODEL": "deepseek-flash",
            "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
            "EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 1024,
        }, Settings())
        values = read_config()
        self.assertEqual(values["LLM_MODE"], "live")
        self.assertEqual(values["EMBEDDING_MODE"], "online")

    def test_runtime_embedding_fields_cannot_be_written_from_the_page(self):
        """页面不能直接改写正在使用的向量模型/维度，只能保存「新设置」。"""
        with self.assertRaises(ValueError) as rejected:
            api_settings.save_for_active_space({"EMBEDDING_MODEL": "text-embedding-v4"}, Settings())
        self.assertIn("新设置", str(rejected.exception))
        # 目标字段可以写（完整性由保存入口另行校验，这里直接走底层服务）
        save_config({"EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 768})
        self.assertEqual(read_config()["EMBEDDING_TARGET_DIMENSIONS"], 768)


class ReadinessTests(unittest.TestCase):
    """必须配置真实 API：没配好就不能假装能用。"""

    def setUp(self):
        root = Path(__file__).parent / '.tmp-api-settings'
        root.mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.folder.cleanup)
        env = patch.dict(os.environ, {"SMARTSKETCH_API_CONFIG": str(Path(self.folder.name) / "config.json")})
        env.start()
        self.addCleanup(env.stop)

    def test_missing_requirements_are_listed_for_users(self):
        labels = api_settings.missing_requirements()
        self.assertIn("大模型 API Key", labels)
        self.assertIn("向量模型", labels)

    def test_status_reports_restart_after_save(self):
        class Active:
            LLM_MODE = "live"
            LLM_CHAT_MODEL = "deepseek-flash"
            EMBEDDING_MODE = "online"
            EMBEDDING_MODEL = "text-embedding-v4"
            EMBEDDING_DIMENSIONS = 1024

        before = api_settings.config_status(Active())
        self.assertFalse(before["ready"])
        self.assertFalse(before["restart_needed"])
        api_settings.save_config({
            "LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_API_KEY": "k", "LLM_CHAT_MODEL": "deepseek-flash",
            "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
            "EMBEDDING_MODEL": "text-embedding-v4",
        })
        after = api_settings.config_status(Active())
        self.assertTrue(after["ready"])
        # 刚保存过的配置还没被进程读到，必须提示重启
        self.assertTrue(after["restart_needed"])

    def test_status_reports_not_ready_while_process_still_demo(self):
        """配置已填好但进程还没重启（仍在演示实现）时，不能算可用。"""
        class Active:
            LLM_MODE = "live"
            LLM_CHAT_MODEL = "deepseek-flash"
            EMBEDDING_MODE = "demo"
            EMBEDDING_MODEL = "text-embedding-v4"
            EMBEDDING_DIMENSIONS = 1024

        api_settings.save_config({
            "LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_API_KEY": "k", "LLM_CHAT_MODEL": "deepseek-flash",
            "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
            "EMBEDDING_MODEL": "text-embedding-v4",
        })
        status = api_settings.config_status(Active())
        self.assertTrue(status["configured"])
        self.assertFalse(status["ready"])
        self.assertTrue(any("向量模型" in label for label in status["missing"]))

    def test_settings_ready_needs_real_services(self):
        class Demo:
            LLM_MODE = "demo"
            EMBEDDING_MODE = "demo"

        self.assertFalse(api_settings.settings_ready(Demo()))
        api_settings.save_config({
            "LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_API_KEY": "k", "LLM_CHAT_MODEL": "deepseek-flash",
            "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
            "EMBEDDING_MODEL": "text-embedding-v4",
        })

        class Live:
            LLM_MODE = "live"
            EMBEDDING_MODE = "online"

        self.assertTrue(api_settings.settings_ready(Live()))


class ApiSettingsDimensionTests(unittest.TestCase):
    """向量维度：新设置与正在使用的配置分开。"""

    def setUp(self):
        root = Path(__file__).parent / '.tmp-api-settings'
        root.mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.folder.cleanup)
        env = patch.dict(os.environ, {"SMARTSKETCH_API_CONFIG": str(Path(self.folder.name) / "config.json")})
        env.start()
        self.addCleanup(env.stop)

    def test_blank_model_keeps_saved_selection(self):
        save_config({"LLM_CHAT_MODEL": "chosen"})
        save_config({"LLM_CHAT_MODEL": ""})
        self.assertEqual(read_config()["LLM_CHAT_MODEL"], "chosen")

    def test_http_local_only(self):
        save_config({"LLM_BASE_URL": "http://127.0.0.1:11434/v1"})
        with self.assertRaises(ValueError):
            save_config({"LLM_BASE_URL": "http://example.com/v1"})

    # ---- 向量维度：目标配置与运行时向量空间分开 ----

    def test_target_dimension_must_be_supported_by_model(self):
        """已登记模型只接受其支持的维度；未登记模型必须显式确认。"""
        with self.assertRaises(ValueError):
            save_config({"EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 999})
        save_config({"EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 768})
        self.assertEqual(read_config()["EMBEDDING_TARGET_DIMENSIONS"], 768)

        with self.assertRaises(ValueError):
            save_config({"EMBEDDING_TARGET_MODEL": "my-private-embedding", "EMBEDDING_TARGET_DIMENSIONS": 512})
        save_config({"EMBEDDING_TARGET_MODEL": "my-private-embedding", "EMBEDDING_TARGET_DIMENSIONS": 512, "EMBEDDING_TARGET_ASSUME_DIMENSIONS": True})
        self.assertEqual(read_config()["EMBEDDING_TARGET_DIMENSIONS"], 512)

    def test_target_dimension_does_not_change_runtime_space(self):
        """保存目标维度不得改写运行时 EMBEDDING_MODEL / EMBEDDING_DIMENSIONS，重启也不会被门禁拦住。"""
        save_config({"EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_DIMENSIONS": 1024})
        save_config({"EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 1536})
        values = read_config()
        self.assertEqual(values["EMBEDDING_DIMENSIONS"], 1024)
        self.assertEqual(values["EMBEDDING_MODEL"], "text-embedding-v4")
        self.assertEqual(values["EMBEDDING_TARGET_DIMENSIONS"], 1536)
        target = target_embedding_space(public_config())
        self.assertEqual((target["model"], target["dimensions"]), ("text-embedding-v4", 1536))

    def test_chat_model_target_body_is_leaked_into_config(self):
        """首次配置：还没有正在使用的向量模型时，新设置直接作为启用配置。"""
        save_config({"EMBEDDING_TARGET_MODEL": "text-embedding-v3"})
        values = read_config()
        self.assertEqual(values["EMBEDDING_TARGET_MODEL"], "text-embedding-v3")
        self.assertEqual(values["EMBEDDING_MODEL"], "text-embedding-v3")

    def test_target_field_never_overwrites_an_existing_runtime_model(self):
        """已有正在使用的向量模型时，新设置只作为「待重新处理」的目标。"""
        save_config({"EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_DIMENSIONS": 1024})
        save_config({"EMBEDDING_TARGET_MODEL": "text-embedding-v3", "EMBEDDING_TARGET_DIMENSIONS": 512})
        values = read_config()
        self.assertEqual(values["EMBEDDING_MODEL"], "text-embedding-v4")
        self.assertEqual(values["EMBEDDING_DIMENSIONS"], 1024)
        self.assertEqual(values["EMBEDDING_TARGET_MODEL"], "text-embedding-v3")

    def test_embedding_test_sends_selected_dimensions(self):
        """可变维度模型：把用户选择的目标维度发给服务商，并校验返回长度。"""
        save_config({"EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
                     "EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_MODEL": "text-embedding-v4", "EMBEDDING_TARGET_DIMENSIONS": 768})
        body = {"model": "text-embedding-v4", "data": [{"embedding": [0.0] * 768}]}
        with patch.object(api_settings, "urlopen", return_value=FakeResponse(body)) as call:
            result = api_settings.test_connection({"kind": "embedding", "EMBEDDING_TARGET_DIMENSIONS": 768})
        self.assertTrue(result["ok"], result.get("error"))
        sent = json.loads(call.call_args.args[0].data)
        self.assertEqual(sent["dimensions"], 768)
        self.assertEqual(result["detail"]["dimensions"], 768)

    def test_fixed_dimension_model_does_not_send_dimensions(self):
        """能力未知/固定维度模型不发 dimensions 参数，避免服务商报错。"""
        save_config({"EMBEDDING_BASE_URL": "http://127.0.0.1:11434/v1", "EMBEDDING_MODEL": "nomic-embed-text"})
        body = {"model": "nomic-embed-text", "data": [{"embedding": [0.0] * 768}]}
        with patch.object(api_settings, "urlopen", return_value=FakeResponse(body)) as call:
            result = api_settings.test_connection({"kind": "embedding", "EMBEDDING_TARGET_DIMENSIONS": 768,
                                                   "EMBEDDING_TARGET_ASSUME_DIMENSIONS": True})
        sent = json.loads(call.call_args.args[0].data)
        self.assertNotIn("dimensions", sent)
        self.assertTrue(result["ok"], result.get("error"))

    def test_capability_accepts_list_path(self):
        """能力查询与模型发现共用表单值：list_path 要被忽略，不能当成未知字段报错。"""
        result = api_settings.embedding_capability("embedding", {
            "EMBEDDING_TARGET_MODEL": "text-embedding-v4",
            "list_path": "/models",
        })
        self.assertTrue(result["known"])
        self.assertEqual(result["default"], 1024)
        with self.assertRaises(ValueError):
            api_settings.embedding_capability("embedding", {"NOT_A_FIELD": "x"})

    def test_returned_length_mismatch_is_reported(self):
        """返回长度与目标维度不一致时必须给出明确错误，而不是静默通过。"""
        save_config({"EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_API_KEY": "k",
                     "EMBEDDING_MODEL": "text-embedding-v4"})
        body = {"model": "text-embedding-v4", "data": [{"embedding": [0.0] * 512}]}
        with patch.object(api_settings, "urlopen", return_value=FakeResponse(body)):
            result = api_settings.test_connection({"kind": "embedding", "EMBEDDING_TARGET_DIMENSIONS": 1024})
        self.assertFalse(result["ok"])
        self.assertIn("不一致", result["error"])
        self.assertIn("512", result["error"])


if __name__ == "__main__":
    unittest.main()
