"""Current user's model configuration (ADR-080). Routes only translate; rules live in the service."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import current_user
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import ModelDiscoveryRequest, ModelDiscoveryResult, ModelConfig, ModelConfigTestRequest, ModelConfigTestResult, ModelConfigUpdate
from app.schemas.errors import Error
from app.services import model_configs as service
from app.services.ai.compatible import HttpTransport
from app.services.ai.outbound import EndpointBlocked, build_transport
from app.services.credentials import ModelConfigRequired

router = APIRouter(prefix="/api/v1/me/model-config", tags=["settings"])

_VALIDATION_MESSAGE = "请求参数不符合要求，请检查标注的字段"
_REQUIRED_MESSAGE = "请先在「模型 API 设置」中保存你的模型 API 配置"
_ERRORS = {401: {"model": Error}, 422: {"model": Error}}


def _plain(value: Any) -> str | None:
    """``format: password`` fields may be generated as ``SecretStr``."""
    if value is None:
        return None
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def _invalid(field: str, reason: str) -> JSONResponse:
    body = Error(code="VALIDATION_ERROR", message=_VALIDATION_MESSAGE,
                 details={"fields": [{"in": "body", "field": field, "reason": reason}]})
    return JSONResponse(status_code=422, content=body.model_dump())


def _disabled() -> JSONResponse:
    body = Error(code="STORAGE_UNAVAILABLE", message="服务端未启用个人模型凭据存储",
                 details={"reason": "credential_store_disabled"})
    return JSONResponse(status_code=503, content=body.model_dump())


def _to_wire(view: service.ModelConfigView) -> dict[str, Any]:
    row = view.row
    if row is None:
        return {"runtime_mode": view.runtime_mode, "configured": False}
    wire: dict[str, Any] = {
        "runtime_mode": view.runtime_mode, "configured": True, "base_url": row.base_url, "model": row.model,
        "key_hint": row.key_hint, "version": row.version, "updated_at": row.updated_at,
        "disable_thinking": row.disable_thinking,
    }
    if row.last_test_at is not None:
        last: dict[str, Any] = {"ok": bool(row.last_test_ok), "tested_at": row.last_test_at}
        if row.last_test_error_class is not None:
            last["error_class"] = row.last_test_error_class
        wire["last_test"] = last
    return wire


def _transport(request: Request) -> HttpTransport:
    return getattr(request.app.state, "model_transport", None) or build_transport(request.app.state.settings)


@router.get("", operation_id="getModelConfig", response_model=ModelConfig, response_model_exclude_none=True,
            responses={401: {"model": Error}})
def get_model_config(request: Request, user: AccountRecord = Depends(current_user)) -> JSONResponse:
    return JSONResponse(content=_to_wire(service.view(request.app.state.settings, user.id)))


@router.put("", operation_id="saveModelConfig", response_model=ModelConfig, response_model_exclude_none=True,
            responses={**_ERRORS, 503: {"model": Error}})
def save_model_config(payload: ModelConfigUpdate, request: Request,
                      user: AccountRecord = Depends(current_user)) -> JSONResponse:
    try:
        view = service.save(request.app.state.settings, user.id, base_url=payload.base_url,
                            model=payload.model, api_key=_plain(payload.api_key),
                            disable_thinking=payload.disable_thinking)
    except EndpointBlocked as blocked:
        return _invalid("base_url", blocked.reason)
    except service.KeyRequired:
        return _invalid("api_key", "required_when_endpoint_changes")
    except service.InvalidKey:
        return _invalid("api_key", "invalid_characters")
    except service.InvalidModel as invalid:
        return _invalid("model", invalid.reason)
    except service.CredentialStoreDisabled:
        return _disabled()
    return JSONResponse(content=_to_wire(view))


@router.delete("", operation_id="clearModelConfig", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response, responses={401: {"model": Error}})
def clear_model_config(request: Request, user: AccountRecord = Depends(current_user)) -> Response:
    service.clear(request.app.state.settings, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/test", operation_id="testModelConfig", response_model=ModelConfigTestResult,
             response_model_exclude_none=True,
             responses={**_ERRORS, 409: {"model": Error}, 429: {"model": Error}, 503: {"model": Error}})
def test_model_config(request: Request, payload: ModelConfigTestRequest | None = None,
                      user: AccountRecord = Depends(current_user)) -> JSONResponse:
    values = (None, None, None) if payload is None else (payload.base_url, payload.model, _plain(payload.api_key))
    if any(value is not None for value in values) and not all(value is not None for value in values):
        missing = next(name for name, value in zip(("base_url", "model", "api_key"), values) if value is None)
        return _invalid(missing, "missing")
    wait = request.app.state.config_test_limiter.acquire(user.id)
    if wait:
        body = Error(code="RATE_LIMITED", message="测试过于频繁，请稍后再试")
        return JSONResponse(status_code=429, content=body.model_dump(exclude_none=True), headers={"Retry-After": str(wait)})
    try:
        outcome = service.run_test(request.app.state.settings, user.id, base_url=values[0], model=values[1],
                                   api_key=values[2], transport=_transport(request),
                                   disable_thinking=bool(payload is not None and payload.disable_thinking))
    except ModelConfigRequired:
        body = Error(code="MODEL_CONFIG_REQUIRED", message=_REQUIRED_MESSAGE)
        return JSONResponse(status_code=409, content=body.model_dump(exclude_none=True))
    except service.InvalidKey:
        return _invalid("api_key", "invalid_characters")
    except service.InvalidModel as invalid:
        return _invalid("model", invalid.reason)
    except service.CredentialStoreDisabled:
        return _disabled()
    wire: dict[str, Any] = {"ok": outcome.ok, "latency_ms": outcome.latency_ms}
    if outcome.error_class is not None:
        wire["error_class"] = outcome.error_class
    return JSONResponse(content=wire)


@router.post("/models", operation_id="discoverModels", response_model=ModelDiscoveryResult,
             response_model_exclude_none=True,
             responses={**_ERRORS, 409: {"model": Error}, 429: {"model": Error}, 503: {"model": Error}})
def discover_models(request: Request, payload: ModelDiscoveryRequest | None = None,
                    user: AccountRecord = Depends(current_user)) -> JSONResponse:
    base_url = payload.base_url if payload is not None else None
    api_key = _plain(payload.api_key) if payload is not None else None
    if api_key is not None and base_url is None:
        return _invalid("base_url", "missing")
    wait = request.app.state.model_discovery_limiter.acquire(user.id)
    if wait:
        body = Error(code="RATE_LIMITED", message="获取模型过于频繁，请稍后再试")
        return JSONResponse(status_code=429, content=body.model_dump(exclude_none=True), headers={"Retry-After": str(wait)})
    try:
        outcome = service.discover_models(request.app.state.settings, user.id, base_url=base_url, api_key=api_key,
                    transport=getattr(request.app.state, "model_discovery_transport", None) or build_transport(request.app.state.settings))
    except ModelConfigRequired:
        body = Error(code="MODEL_CONFIG_REQUIRED", message=_REQUIRED_MESSAGE)
        return JSONResponse(status_code=409, content=body.model_dump(exclude_none=True))
    except service.KeyRequired:
        return _invalid("api_key", "required_when_endpoint_changes")
    except service.InvalidKey:
        return _invalid("api_key", "invalid_characters")
    except service.CredentialStoreDisabled:
        return _disabled()
    wire = {"ok": outcome.ok, "models": outcome.models}
    if outcome.error_class is not None:
        wire["error_class"] = outcome.error_class
    return JSONResponse(content=wire)
