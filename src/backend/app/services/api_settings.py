"""Local portable API configuration. Secrets never appear in API responses."""
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

LOCK = threading.RLock()
FIELDS = {"LLM_MODE", "LLM_BASE_URL", "LLM_API_KEY", "LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "LLM_PROVIDER_LABEL", "EMBEDDING_MODE", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "EMBEDDING_PROVIDER_LABEL"}
SECRETS = {"LLM_API_KEY", "EMBEDDING_API_KEY"}
KEEP_WHEN_BLANK = {"LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "EMBEDDING_MODEL", "LLM_PROVIDER_LABEL", "EMBEDDING_PROVIDER_LABEL", *SECRETS}
TIMEOUT_SECONDS = 20
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

def _is_local_host(name):
    import ipaddress
    if name in LOCAL_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(name)
        return address in ipaddress.ip_network("192.168.0.0/16") or address in ipaddress.ip_network("10.0.0.0/8")
    except ValueError:
        return False
def _secret_value(value, encrypt=False):
    """Use Windows user-bound DPAPI encryption for persisted keys."""
    if os.name != "nt" or not value:
        return value
    import base64
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]
    if not encrypt and not value.startswith("dpapi:"):
        return value
    raw = value.encode() if encrypt else base64.b64decode(value[6:])
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("本机密钥无法读取或保存")
    try:
        output = ctypes.string_at(target.data, target.size)
        return "dpapi:" + base64.b64encode(output).decode() if encrypt else output.decode()
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))
DEFAULTS = {"LLM_MODE": "demo", "LLM_BASE_URL": "", "LLM_CHAT_MODEL": "", "LLM_EXTRACTION_MODEL": "", "LLM_PROVIDER_LABEL": "", "EMBEDDING_MODE": "demo", "EMBEDDING_BASE_URL": "", "EMBEDDING_MODEL": "", "EMBEDDING_DIMENSIONS": 1024, "EMBEDDING_PROVIDER_LABEL": ""}

def config_path():
    return Path(os.environ.get("SMARTSKETCH_API_CONFIG") or (Path(os.environ.get("LOCALAPPDATA", ".")) / "SmartSketch-External" / "api-settings.json"))

def read_config():
    with LOCK:
        path = config_path()
        values = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        for name in SECRETS:
            if name in values:
                values[name] = _secret_value(values[name])
        return values

def validate_config(values):
    if set(values) - FIELDS:
        raise ValueError("未知配置字段")
    for name, value in values.items():
        if name == "EMBEDDING_DIMENSIONS":
            if type(value) is not int or value != 1024:
                raise ValueError("当前版本使用 1024 维向量")
        elif not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
            raise ValueError("配置格式错误")
        if name.endswith("BASE_URL") and value:
            try:
                parsed = urlsplit(value)
                valid_scheme = parsed.scheme == "https" or (parsed.scheme == "http" and _is_local_host(parsed.hostname))
                if not valid_scheme or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port == 0 or any(c.isspace() for c in value):
                    raise ValueError("API 地址必须为 HTTPS；本机地址可用 HTTP")
            except ValueError:
                raise ValueError("API 地址必须为 HTTPS；本机地址可用 HTTP") from None
    if values.get("LLM_MODE", "demo") not in ("demo", "live") or values.get("EMBEDDING_MODE", "demo") not in ("demo", "online"):
        raise ValueError("运行模式错误")

def save_config(values):
    validate_config(values)
    with LOCK:
        merged = DEFAULTS | read_config()
        merged.update({k: v.strip() if isinstance(v, str) else v for k, v in values.items() if k not in KEEP_WHEN_BLANK or v.strip()})
        # 聊天与知识抽取共用同一个大模型：只给其中一个字段时另一个同步，避免后台任务用错模型
        chat = merged.get("LLM_CHAT_MODEL") or merged.get("LLM_EXTRACTION_MODEL")
        if chat:
            merged["LLM_CHAT_MODEL"] = merged["LLM_EXTRACTION_MODEL"] = chat
        for mode, required in (("LLM_MODE", ("LLM_API_KEY",)), ("EMBEDDING_MODE", ("EMBEDDING_API_KEY",))):
            if merged[mode] != "demo" and any(not merged.get(k) for k in required):
                raise ValueError("启用在线模式前需填写密钥")
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        stored = merged | {name: _secret_value(merged[name], encrypt=True) for name in SECRETS if name in merged}
        temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        return public_config()

def public_config():
    values = DEFAULTS | read_config()
    # 旧配置可能只写了知识抽取模型：界面统一显示同一个大模型
    if not values.get("LLM_CHAT_MODEL") and values.get("LLM_EXTRACTION_MODEL"):
        values["LLM_CHAT_MODEL"] = values["LLM_EXTRACTION_MODEL"]
    return {k: v for k, v in values.items() if k not in SECRETS} | {k + "_configured": bool(values.get(k)) for k in SECRETS}

import json
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from time import perf_counter

class _CallError(ValueError):
    def __init__(self, message, latency_ms, http_status=None):
        super().__init__(message)
        self.latency_ms = latency_ms
        self.http_status = http_status

def _api_base(value):
    base = value.strip().rstrip("/")
    if not base:
        raise ValueError("请填写 API 地址")
    validate_config({"LLM_BASE_URL": base})
    return base + "/v1" if not urlsplit(base).path else base

def _call_json(url, key, payload=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = UrlRequest(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    started = perf_counter()
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read(2_000_000).decode("utf-8"))
            status = getattr(response, "status", 200)
        return body, round((perf_counter() - started) * 1000), status
    except HTTPError as exc:
        raise _CallError(f"服务商返回 HTTP {exc.code}，请核对密钥、地区、模型与额度", round((perf_counter() - started) * 1000), exc.code) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _CallError("服务商响应不是 JSON，请确认 API 地址", round((perf_counter() - started) * 1000)) from None
    except (URLError, TimeoutError, OSError):
        raise _CallError("连接失败，请检查网络、API 地址与证书", round((perf_counter() - started) * 1000)) from None

def extract_model_options(body):
    """兼容常见 OpenAI 兼容接口的模型列表返回，规范化为 [{id, name}]。

    支持 data: [{id, name}]、models: [{id, name}]、字符串数组，以及 data 为
    {"models": [...]} 的包裹；按 id 去重并保留首次出现的顺序，空值丢弃。
    """
    entries = body
    if isinstance(body, dict):
        entries = body.get("data", body.get("models", []))
        if isinstance(entries, dict):
            entries = entries.get("models", entries.get("data", []))
    if not isinstance(entries, list):
        return []
    options = []
    seen = set()
    for item in entries:
        if isinstance(item, str):
            identifier, label = item, ""
        elif isinstance(item, dict):
            identifier = item.get("id") or item.get("name") or item.get("model")
            label = item.get("name") or item.get("display_name") or ""
        else:
            continue
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        identifier = identifier.strip()
        if identifier in seen:
            continue
        seen.add(identifier)
        options.append({"id": identifier, "name": label.strip() if isinstance(label, str) else ""})
    return options


def extract_model_ids(body):
    """模型 ID 列表；保留该字段以兼容既有调用方。"""
    return [option["id"] for option in extract_model_options(body)]


def _model_options_from_ids(models):
    return [{"id": name, "name": ""} for name in models]


def _looks_like_embedding(name):
    return any(word in name.lower() for word in ("embed", "bge", "gte", "m3e", "text-similarity", "rerank"))

def _resolve(kind, body):
    if kind not in ("llm", "embedding"):
        raise ValueError("测试类型错误")
    supplied = {k: v for k, v in body.items() if k != "kind"}
    validate_config(supplied)
    values = DEFAULTS | read_config() | {k: v.strip() if isinstance(v, str) else v for k, v in supplied.items() if k not in KEEP_WHEN_BLANK or v.strip()}
    prefix = "EMBEDDING" if kind == "embedding" else "LLM"
    base = _api_base(values[prefix + "_BASE_URL"])
    key = values.get(prefix + "_API_KEY", "")
    if not key and not _is_local_host(urlsplit(base).hostname):
        raise ValueError("请填写 API Key")
    return prefix, base, key

def list_models(kind, body):
    if kind not in ("llm", "embedding"):
        raise ValueError("测试类型错误")
    result = {"kind": kind, "ok": False, "models": [], "model_options": [], "count": 0, "latency_ms": None, "provider": "", "error": None}
    try:
        # list_path 仅用于本次模型发现，不属于持久配置字段。
        config_body = {k: v for k, v in body.items() if k != "list_path"}
        _, result["provider"], key = _resolve(kind, config_body)
        # 个别服务商的模型列表不在 /models 下，允许请求体给出路径（预设里带）
        path = (body.get("list_path") or "").strip() or "/models"
        if not path.startswith("/"):
            raise ValueError("模型列表路径必须以 / 开头")
        response, result["latency_ms"], _ = _call_json(result["provider"] + path, key)
        options = extract_model_options(response)
        if kind == "embedding":
            # 只有在接口确实带能力信息时才算筛选；仅凭名称命中关键字只做「优先展示」，不排除其它
            matched = [option for option in options if _looks_like_embedding(option["id"])]
            if matched:
                options = matched + [option for option in options if option not in matched]
        if not options:
            raise ValueError("接口未返回可识别的模型列表，可手动填写模型 ID")
        result.update(ok=True, models=[option["id"] for option in options], model_options=options, count=len(options))
    except ValueError as exc:
        result["error"] = str(exc)
        result["latency_ms"] = getattr(exc, "latency_ms", result["latency_ms"])
    return result

def test_connection(body):
    kind = body.get("kind", "llm")
    if kind not in ("llm", "embedding"):
        raise ValueError("测试类型错误")
    result = {"kind": kind, "ok": False, "latency_ms": None, "http_status": None, "detail": {}, "provider": "", "error": None}
    try:
        prefix, result["provider"], key = _resolve(kind, body)
        saved = read_config()
        model_field = "EMBEDDING_MODEL" if kind == "embedding" else "LLM_CHAT_MODEL"
        model = body.get(model_field, "").strip() or saved.get(model_field, "")
        if kind == "llm" and not model:
            model = body.get("LLM_EXTRACTION_MODEL", "").strip() or saved.get("LLM_EXTRACTION_MODEL", "")
        if not model:
            raise ValueError("请先获取并选择一个模型，或手动填写模型名")
        result["detail"]["model"] = model
        payload = {"model": model, "input": ["连接测试"], "dimensions": 1024} if kind == "embedding" else {"model": model, "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 5}
        path = "/embeddings" if kind == "embedding" else "/chat/completions"
        response, result["latency_ms"], result["http_status"] = _call_json(result["provider"] + path, key, payload)
        if kind == "embedding":
            data = response.get("data") if isinstance(response, dict) else None
            vector = data[0].get("embedding") if isinstance(data, list) and data and isinstance(data[0], dict) else None
            if not isinstance(vector, list) or not vector:
                raise ValueError("响应缺少向量数据，请确认接口支持 embeddings")
            result["detail"]["dimensions"] = len(vector)
        else:
            choices = response.get("choices") if isinstance(response, dict) else None
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("响应缺少 choices，请确认接口支持 chat/completions")
            result["detail"]["model"] = choices[0].get("model") or model
        result["ok"] = True
    except ValueError as exc:
        result.update(error=str(exc), latency_ms=getattr(exc, "latency_ms", result["latency_ms"]), http_status=getattr(exc, "http_status", result["http_status"]))
    return result
def save_for_active_space(body, settings):
    validate_config(body)
    target = body.get("EMBEDDING_MODE", public_config()["EMBEDDING_MODE"])
    model = body.get("EMBEDDING_MODEL", public_config()["EMBEDDING_MODEL"])
    target_base = body.get("EMBEDDING_BASE_URL", public_config()["EMBEDDING_BASE_URL"]).rstrip("/")
    if target != settings.EMBEDDING_MODE or (target == "online" and (model != settings.EMBEDDING_MODEL or target_base != settings.EMBEDDING_BASE_URL.rstrip("/"))):
        raise ValueError("更换向量模型需要离线迁移；请先完成迁移，或保留当前向量模式后保存其他配置。")
    return save_config(body)
