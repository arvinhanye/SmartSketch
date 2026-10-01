"""向量模型能力表：支持的输出维度、默认维度、是否可用 ``dimensions`` 参数调整。

只登记**已核对过供应商官方文档**的模型；没登记的模型一律视为「能力未知」，
由用户手动填写维度并显式确认，不做任何推测（AGENTS.md §4：文档是实现的约束）。
每条记录都带 ``source``，便于日后复核。
"""

from urllib.parse import urlsplit

#: 能力未知时返回的标记
UNKNOWN = "unknown"
#: 固定维度：接口不接受 dimensions 调整
FIXED = "fixed"
#: 可通过 dimensions 参数在支持集合内调整
FLEXIBLE = "flexible"

# model id -> 能力
_MODEL_CAPABILITIES: dict[str, dict] = {
    # 阿里云百炼（通义）兼容模式：官方文档给出枚举，v4 支持 8 档、默认 1024
    # https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/
    "text-embedding-v4": {
        "provider": "dashscope",
        "dimensions": (64, 128, 256, 512, 768, 1024, 1536, 2048),
        "default": 1024,
        "flexible": FLEXIBLE,
        "label": "通义 text-embedding-v4",
        "source": "https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/",
    },
    "text-embedding-v3": {
        "provider": "dashscope",
        "dimensions": (512, 768, 1024),
        "default": 1024,
        "flexible": FLEXIBLE,
        "label": "通义 text-embedding-v3",
        "source": "https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/",
    },
    # OpenAI：text-embedding-3 系列支持 dimensions 缩短输出（官方发布说明与 API 参考）
    "text-embedding-3-small": {
        "provider": "openai",
        "dimensions": (512, 1536),
        "default": 1536,
        "flexible": FLEXIBLE,
        "label": "OpenAI text-embedding-3-small",
        "source": "https://platform.openai.com/docs/guides/embeddings",
    },
    "text-embedding-3-large": {
        "provider": "openai",
        "dimensions": (256, 1024, 3072),
        "default": 3072,
        "flexible": FLEXIBLE,
        "label": "OpenAI text-embedding-3-large",
        "source": "https://platform.openai.com/docs/guides/embeddings",
    },
}

#: 需要用户显式确认「按该维度调用」的自定义模型标记
ASSUME_FLAG = "EMBEDDING_TARGET_ASSUME_DIMENSIONS"


def capability_for(model: str) -> dict:
    """按模型 ID 取能力；未登记返回 ``known=False``，不猜维度。"""
    entry = _MODEL_CAPABILITIES.get((model or "").strip())
    if entry is None:
        return {
            "known": False,
            "model": model,
            "dimensions": [],
            "default": None,
            "flexible": UNKNOWN,
            "label": "",
            "source": "",
        }
    return {
        "known": True,
        "model": model,
        "dimensions": list(entry["dimensions"]),
        "default": entry["default"],
        "flexible": entry["flexible"],
        "label": entry["label"],
        "source": entry["source"],
    }


def supports_dimension_parameter(model: str) -> bool:
    """是否可以把 ``dimensions`` 放进请求（只有已确认可调的模型才发）。"""
    return capability_for(model)["flexible"] == FLEXIBLE


def validate_target_dimension(model: str, dimensions: int, assume: bool = False) -> None:
    """校验目标维度：正整数；已登记模型必须落在支持集合内；未知模型要求显式确认。"""
    if type(dimensions) is not int or dimensions < 1:
        raise ValueError("向量维度必须是正整数")
    capability = capability_for(model)
    if not capability["known"]:
        if not assume:
            raise ValueError(
                "该模型的维度能力未知：请手动填写维度，并勾选「按该维度调用」以确认使用。"
            )
        return
    if dimensions not in capability["dimensions"]:
        allowed = "、".join(str(value) for value in capability["dimensions"])
        raise ValueError(
            f"{capability['label'] or model} 不支持 {dimensions} 维；可选：{allowed}。"
        )


def provider_from_base_url(base_url: str) -> str:
    host = ""
    try:
        host = (urlsplit(base_url or "").hostname or "").lower()
    except ValueError:
        host = ""
    if host.endswith("dashscope.aliyuncs.com") or host.endswith("qwencloudapi.com"):
        return "dashscope"
    if host.endswith("openai.com"):
        return "openai"
    return ""
