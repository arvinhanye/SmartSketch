"""Local portable API configuration. Secrets never appear in API responses."""
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from app.services.embedding_models import (
    ASSUME_FLAG,
    capability_for,
    provider_from_base_url,
    supports_dimension_parameter,
    validate_target_dimension,
)

LOCK = threading.RLock()
FIELDS = {"LLM_MODE", "LLM_BASE_URL", "LLM_API_KEY", "LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "LLM_PROVIDER_LABEL", "EMBEDDING_MODE", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS", "EMBEDDING_PROVIDER_LABEL", "EMBEDDING_TARGET_MODEL", "EMBEDDING_TARGET_DIMENSIONS", ASSUME_FLAG}
SECRETS = {"LLM_API_KEY", "EMBEDDING_API_KEY"}
KEEP_WHEN_BLANK = {"LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "EMBEDDING_MODEL", "LLM_PROVIDER_LABEL", "EMBEDDING_PROVIDER_LABEL", "EMBEDDING_TARGET_MODEL", *SECRETS}
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
DEFAULTS = {"LLM_MODE": "demo", "LLM_BASE_URL": "", "LLM_CHAT_MODEL": "", "LLM_EXTRACTION_MODEL": "", "LLM_PROVIDER_LABEL": "", "EMBEDDING_MODE": "demo", "EMBEDDING_BASE_URL": "", "EMBEDDING_MODEL": "", "EMBEDDING_DIMENSIONS": 1024, "EMBEDDING_PROVIDER_LABEL": "", "EMBEDDING_TARGET_MODEL": "", "EMBEDDING_TARGET_DIMENSIONS": 0, ASSUME_FLAG: False}

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
            # 运行时维度：启动门禁要求与数据库索引一致，这里只做正整数校验
            if type(value) is not int or value < 1:
                raise ValueError("向量维度必须是正整数")
        elif name == "EMBEDDING_TARGET_DIMENSIONS":
            if type(value) is not int or value < 0:
                raise ValueError("目标向量维度必须是 0（未设置）或正整数")
        elif name == ASSUME_FLAG:
            if type(value) is not bool:
                raise ValueError("配置格式错误")
        else:
            _validate_string_field(name, value)
    if values.get("LLM_MODE", "demo") not in ("demo", "live") or values.get("EMBEDDING_MODE", "demo") not in ("demo", "online"):
        raise ValueError("运行模式错误")


def _validate_string_field(name, value):
    """字符串字段的通用校验：长度、控制字符，以及 API 地址必须 HTTPS（本机可 HTTP）。"""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError("配置格式错误")
    if name.endswith("BASE_URL") and value:
        try:
            parsed = urlsplit(value)
            valid_scheme = parsed.scheme == "https" or (parsed.scheme == "http" and _is_local_host(parsed.hostname))
            if not valid_scheme or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port == 0 or any(c.isspace() for c in value):
                raise ValueError("API 地址必须为 HTTPS；本机地址可用 HTTP")
        except ValueError:
            raise ValueError("API 地址必须为 HTTPS；本机地址可用 HTTP") from None

def require_complete(values=None):
    """保存入口的完整性检查：必须配好真实的大模型与向量模型，才允许保存生效。

    面向用户的说法，只提「要填什么」，不提内部字段。还没启用向量模型时，页面上的
    「新设置」就足够（保存后即成为启用配置）。
    """
    values = DEFAULTS | read_config() if values is None else values
    if not values.get("EMBEDDING_MODEL") and values.get("EMBEDDING_TARGET_MODEL"):
        values = values | {"EMBEDDING_MODEL": values["EMBEDDING_TARGET_MODEL"]}
    if missing_requirements(values):
        raise ValueError("请选择大模型和向量模型，并填写对应的 API Key。")


def save_config(values):
    validate_config(values)
    with LOCK:
        merged = DEFAULTS | read_config()
        merged.update({k: v.strip() if isinstance(v, str) else v for k, v in values.items() if k not in KEEP_WHEN_BLANK or v.strip()})
        # 只用真实服务：不再提供演示模式（模式字段只由本机环境变量或配置决定，不接受演示取值）
        merged["LLM_MODE"] = "live"
        if merged.get("EMBEDDING_MODE") in ("demo", "fake", ""):
            merged["EMBEDDING_MODE"] = "online"
        # 聊天与知识抽取共用同一个大模型：只给其中一个字段时另一个同步，避免后台任务用错模型
        chat = merged.get("LLM_CHAT_MODEL") or merged.get("LLM_EXTRACTION_MODEL")
        if chat:
            merged["LLM_CHAT_MODEL"] = merged["LLM_EXTRACTION_MODEL"] = chat
        # 完整性只由用户保存入口校验（见 save_for_active_space → require_complete）；
        # 这里保持宽松，方便工具与分步保存。
        # 目标向量空间：只做校验与记录，不改变运行时使用的 EMBEDDING_MODEL/EMBEDDING_DIMENSIONS
        if merged.get("EMBEDDING_TARGET_DIMENSIONS"):
            # 目标模型缺失时按当前模型校验（多为固定维度模型，维度必须与之一致）
            target_model = merged.get("EMBEDDING_TARGET_MODEL") or merged.get("EMBEDDING_MODEL")
            validate_target_dimension(target_model, merged["EMBEDDING_TARGET_DIMENSIONS"], bool(merged.get(ASSUME_FLAG)))
        else:
            merged["EMBEDDING_TARGET_DIMENSIONS"] = 0
        # 首次配置：还没有正在使用的向量模型时，新设置直接作为启用配置，装好重启即可使用
        if not merged.get("EMBEDDING_MODEL") and merged.get("EMBEDDING_TARGET_MODEL"):
            merged["EMBEDDING_MODEL"] = merged["EMBEDDING_TARGET_MODEL"]
            merged["EMBEDDING_DIMENSIONS"] = merged.get("EMBEDDING_TARGET_DIMENSIONS") or merged["EMBEDDING_DIMENSIONS"]
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
    # 向量维度页面上要显示，但它不是可自由编辑的配置项
    values["EMBEDDING_DIMENSIONS"] = int(values.get("EMBEDDING_DIMENSIONS") or 0)
    return {k: v for k, v in values.items() if k not in SECRETS} | {k + "_configured": bool(values.get(k)) for k in SECRETS}


#: 缺少哪些配置就不能正常工作（面向用户的字段名）
REQUIRED_FIELDS = (
    ("LLM_BASE_URL", "大模型 API 地址"),
    ("LLM_API_KEY", "大模型 API Key"),
    ("LLM_CHAT_MODEL", "大模型"),
    ("EMBEDDING_BASE_URL", "向量模型 API 地址"),
    ("EMBEDDING_API_KEY", "向量模型 API Key"),
    ("EMBEDDING_MODEL", "向量模型"),
)


def missing_requirements(values=None):
    values = DEFAULTS | read_config() if values is None else values
    return [label for name, label in REQUIRED_FIELDS if not values.get(name)]


def settings_ready(settings) -> bool:
    """本进程是否已具备使用智能功能的条件（真实大模型 + 真实向量模型）。

    没配好时调用方应提示用户去「API 设置」，不得回退到演示实现。
    """
    if settings.LLM_MODE != "live" or settings.EMBEDDING_MODE not in ("online", "local"):
        return False
    return not missing_requirements()


def _not_live_labels(active) -> list[str]:
    """本进程仍在用非真实实现时，按用户能看懂的说法列出原因。"""
    labels: list[str] = []
    if active.LLM_MODE != "live":
        labels.append("大模型（完成设置后重启软件）")
    if active.EMBEDDING_MODE not in ("online", "local"):
        labels.append("向量模型（完成设置后重启软件）")
    return labels


def config_status(active, environ=None):
    """配置状态：是否已配好、是否需要重启才生效、当前实际在用什么模型。

    只用真实服务：``ready`` 为假时前端只引导用户去「API 设置」，不去假装还能用。
    即使配置文件已经填好，只要本进程还没重启、仍在用演示实现，也一律算未就绪。
    """
    values = DEFAULTS | read_config()
    missing = missing_requirements(values) + _not_live_labels(active)
    ready = not missing
    # 保存后还没加载到进程里：配置文件比进程启动时间新，就是不重启不生效
    from app.services.startup_clock import process_started_at

    restart_needed = False
    try:
        path = config_path()
        if path.exists() and path.stat().st_mtime > process_started_at():
            restart_needed = True
    except OSError:
        restart_needed = False
    return {
        "ready": ready,
        # configured 只表示「该填的都填了」，是否可用还取决于进程有没有用上（ready）
        "configured": not missing_requirements(values),
        "restart_needed": restart_needed,
        "missing": missing,
        "active": {
            "LLM_MODE": active.LLM_MODE,
            "LLM_CHAT_MODEL": active.LLM_CHAT_MODEL,
            "EMBEDDING_MODE": active.EMBEDDING_MODE,
            "EMBEDDING_MODEL": active.EMBEDDING_MODEL,
            "EMBEDDING_DIMENSIONS": int(active.EMBEDDING_DIMENSIONS),
        },
    }


def target_embedding_space(values):
    """目标向量空间（待启用配置）：模型与维度，缺省回落到当前模型。"""
    model = values.get("EMBEDDING_TARGET_MODEL") or values.get("EMBEDDING_MODEL") or ""
    dimensions = values.get("EMBEDDING_TARGET_DIMENSIONS") or 0
    return {"model": model, "dimensions": dimensions, "assumed": bool(values.get(ASSUME_FLAG))}


def embedding_capability(kind, body):
    """向量模型能力：只报告已核对官方文档的模型，未登记即「能力未知」。"""
    if kind not in ("llm", "embedding"):
        raise ValueError("测试类型错误")
    supplied = {k: v for k, v in (body or {}).items() if k not in ("kind", "list_path")}
    validate_config(supplied)
    values = DEFAULTS | read_config() | supplied
    model = (body or {}).get("EMBEDDING_TARGET_MODEL") or values.get("EMBEDDING_MODEL") or ""
    capability = capability_for(model)
    capability["provider"] = provider_from_base_url(values.get("EMBEDDING_BASE_URL", ""))
    capability["base_url"] = values.get("EMBEDDING_BASE_URL", "")
    return capability

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
        # 按状态码给用户可以照着做的提示，不暴露原始响应
        if exc.code in (401, 403):
            hint = "API Key 不正确或没有权限，请检查后重新填写"
        elif exc.code == 404:
            hint = "接口地址或模型名称不正确，请检查后重试"
        elif exc.code == 429:
            hint = "调用次数过多或额度不足，请稍后再试或检查账户额度"
        elif exc.code >= 500:
            hint = "服务商暂时不可用，请稍后重试"
        else:
            hint = "请求被服务商拒绝，请检查地址、模型与 API Key"
        raise _CallError(hint, round((perf_counter() - started) * 1000), exc.code) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _CallError("返回内容无法识别，请确认接口地址是否正确", round((perf_counter() - started) * 1000)) from None
    except (URLError, TimeoutError, OSError):
        raise _CallError("连接失败，请检查网络与接口地址", round((perf_counter() - started) * 1000)) from None

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
        if kind == "embedding":
            # 能力只来自能力表；未登记即「未知」，绝不按名称推测
            result["capabilities"] = {
                option["id"]: capability_for(option["id"]) for option in options
            }
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
        if kind == "embedding":
            # 目标配置优先：表单里刚选的模型/维度 → 已保存的目标 → 运行时配置
            model = (body.get("EMBEDDING_TARGET_MODEL") or "").strip() or saved.get("EMBEDDING_TARGET_MODEL") or saved.get("EMBEDDING_MODEL", "")
            dimensions = body.get("EMBEDDING_TARGET_DIMENSIONS") or saved.get("EMBEDDING_TARGET_DIMENSIONS") or saved.get("EMBEDDING_DIMENSIONS") or 0
        else:
            model_field = "LLM_CHAT_MODEL"
            model = body.get(model_field, "").strip() or saved.get(model_field, "")
            dimensions = 0
        if kind == "llm" and not model:
            model = body.get("LLM_EXTRACTION_MODEL", "").strip() or saved.get("LLM_EXTRACTION_MODEL", "")
        if not model:
            raise ValueError("请先获取并选择一个模型，或手动填写模型名")
        result["detail"]["model"] = model
        if kind == "embedding":
            capability = capability_for(model)
            assume = bool(body.get(ASSUME_FLAG) or saved.get(ASSUME_FLAG))
            if not dimensions:
                dimensions = capability["default"] or 0
            if not dimensions:
                raise ValueError("请选择该模型支持的向量维度（能力未知的模型需手动填写并确认）")
            validate_target_dimension(model, dimensions, assume)
            payload = {"model": model, "input": ["连接测试"]}
            if supports_dimension_parameter(model):
                payload["dimensions"] = dimensions
            expected = dimensions
        else:
            payload = {"model": model, "messages": [{"role": "user", "content": "Reply OK"}], "max_tokens": 5}
            expected = 0
        path = "/embeddings" if kind == "embedding" else "/chat/completions"
        response, result["latency_ms"], result["http_status"] = _call_json(result["provider"] + path, key, payload)
        if kind == "embedding":
            data = response.get("data") if isinstance(response, dict) else None
            vector = data[0].get("embedding") if isinstance(data, list) and data and isinstance(data[0], dict) else None
            if not isinstance(vector, list) or not vector:
                raise ValueError("接口没有返回向量数据，请确认这个模型支持文本向量")
            result["detail"]["dimensions"] = len(vector)
            result["detail"]["requested_dimensions"] = expected
            # 返回长度必须与所选维度一致，否则新数据无法与课程内容一起使用
            if expected and len(vector) != expected:
                raise ValueError(
                    f"该模型返回 {len(vector)} 维，与选择的 {expected} 维不一致，请改选它支持的维度。"
                )
        else:
            choices = response.get("choices") if isinstance(response, dict) else None
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("接口没有返回对话结果，请确认这个模型支持对话")
            result["detail"]["model"] = choices[0].get("model") or model
        result["ok"] = True
    except ValueError as exc:
        result.update(error=str(exc), latency_ms=getattr(exc, "latency_ms", result["latency_ms"]), http_status=getattr(exc, "http_status", result["http_status"]))
    return result
def save_for_active_space(body, settings):
    """保存设置。

    向量模型与维度以「新设置」形式保存到 ``EMBEDDING_TARGET_*``：现有课程内容仍按原设置生成向量，
    用户需要在课程页点「重新处理资料」，处理完成后才会启用新设置。页面不直接改写正在使用中的
    向量模型或维度，避免新旧数据混用。
    """
    rejected = [name for name in ("EMBEDDING_MODEL", "EMBEDDING_DIMENSIONS") if name in body]
    if rejected:
        raise ValueError("向量模型与维度请通过「新设置」保存，处理完资料后才会启用。")
    require_complete(DEFAULTS | read_config() | {k: v for k, v in body.items() if k not in KEEP_WHEN_BLANK or (isinstance(v, str) and v.strip())})
    return save_config(body)
