"""Local portable API configuration. Secrets never appear in API responses."""
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

LOCK = threading.RLock()
FIELDS = {"LLM_MODE", "LLM_BASE_URL", "LLM_API_KEY", "LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "EMBEDDING_MODE", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS"}
SECRETS = {"LLM_API_KEY", "EMBEDDING_API_KEY"}
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
DEFAULTS = {"LLM_MODE": "demo", "LLM_BASE_URL": "https://api.deepseek.com/v1", "LLM_CHAT_MODEL": "deepseek-chat", "LLM_EXTRACTION_MODEL": "deepseek-chat", "EMBEDDING_MODE": "demo", "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1", "EMBEDDING_MODEL": "text-embedding-v4", "EMBEDDING_DIMENSIONS": 1024}

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
        if name.endswith("BASE_URL"):
            try:
                parsed = urlsplit(value)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError("API 地址必须为 HTTPS 地址")
            except ValueError:
                raise ValueError("API 地址格式错误") from None
    if values.get("LLM_MODE", "demo") not in ("demo", "live") or values.get("EMBEDDING_MODE", "demo") not in ("demo", "online"):
        raise ValueError("运行模式错误")

def save_config(values):
    validate_config(values)
    with LOCK:
        merged = DEFAULTS | read_config()
        merged.update({k: v.strip() if isinstance(v, str) else v for k, v in values.items() if k not in SECRETS or v.strip()})
        for mode, required in (("LLM_MODE", ("LLM_API_KEY", "LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL")), ("EMBEDDING_MODE", ("EMBEDDING_API_KEY", "EMBEDDING_MODEL"))):
            if merged[mode] != "demo" and any(not merged.get(k) for k in required):
                raise ValueError("启用在线模式前需填写密钥和模型")
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        stored = merged | {name: _secret_value(merged[name], encrypt=True) for name in SECRETS if name in merged}
        temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        return public_config()

def public_config():
    values = DEFAULTS | read_config()
    return {k: v for k, v in values.items() if k not in SECRETS} | {k + "_configured": bool(values.get(k)) for k in SECRETS}

import json
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
def save_for_active_space(body, settings):
    validate_config(body)
    target = body.get("EMBEDDING_MODE", public_config()["EMBEDDING_MODE"])
    model = body.get("EMBEDDING_MODEL", public_config()["EMBEDDING_MODEL"])
    target_base = body.get("EMBEDDING_BASE_URL", public_config()["EMBEDDING_BASE_URL"]).rstrip("/")
    if target != settings.EMBEDDING_MODE or (target == "online" and (model != settings.EMBEDDING_MODEL or target_base != settings.EMBEDDING_BASE_URL.rstrip("/"))):
        raise ValueError("更换向量模型需要离线迁移；请先完成迁移，或保留当前向量模式后保存其他配置。")
    return save_config(body)
def test_settings(body: dict):
    kind = body.pop("kind", "llm")
    if kind not in ("llm", "embedding"):
        raise ValueError("测试类型错误")
    try:
        validate_config(body)
        values = DEFAULTS | read_config() | {k: v for k, v in body.items() if not k.endswith("API_KEY") or v}
        prefix = "EMBEDDING" if kind == "embedding" else "LLM"
        key = values.get(prefix + "_API_KEY", "")
        if not key:
            raise ValueError("请填写 API Key")
        data = {"model": values["EMBEDDING_MODEL"], "input": ["连接测试"], "dimensions": 1024} if kind == "embedding" else {"model": values["LLM_CHAT_MODEL"], "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 5}
        suffix = "/embeddings" if kind == "embedding" else "/chat/completions"
        request = UrlRequest(values[prefix + "_BASE_URL"].rstrip("/") + suffix, data=json.dumps(data).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(2_000_000))
        if kind == "embedding" and len(result["data"][0]["embedding"]) != 1024:
            raise ValueError("向量维度不匹配")
        if kind != "embedding" and not result.get("choices"):
            raise ValueError("模型响应格式不匹配")
        return {"message": "连接成功"}
    except HTTPError as exc:
        raise ValueError(f"服务商返回 HTTP {exc.code}，请核对密钥、地区、模型和额度。") from None
    except (URLError, TimeoutError, OSError, KeyError, ValueError):
        raise ValueError("连接失败，请检查网络、API 地址、密钥和模型配置。") from None
