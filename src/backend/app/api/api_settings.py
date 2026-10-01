"""Teacher-only portable API configuration adapters."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.api.dependencies import teacher_account
from app.services.api_settings import (
    config_status,
    embedding_capability,
    list_models,
    public_config,
    save_for_active_space,
    target_embedding_space,
    test_connection,
)

router = APIRouter(prefix="/api/v1/api-settings", tags=["api-settings"], dependencies=[Depends(teacher_account)])

@router.get("")
def get_settings(request: Request):
    settings = request.app.state.settings
    values = public_config()
    return values | {
        # active：本次进程实际使用的配置；target：页面上待启用的目标配置（需重新处理资料后生效）
        "active": {"LLM_MODE": settings.LLM_MODE, "EMBEDDING_MODE": settings.EMBEDDING_MODE, "EMBEDDING_MODEL": settings.EMBEDDING_MODEL, "EMBEDDING_DIMENSIONS": settings.EMBEDDING_DIMENSIONS},
        "target": target_embedding_space(values),
    }

@router.get("/status")
def get_status(request: Request):
    """是否已配置好、是否需要重启才生效；没配好时前端只把人引导到本页。"""
    return config_status(request.app.state.settings)

@router.put("")
def put_settings(body: dict, request: Request):
    try:
        return save_for_active_space(body, request.app.state.settings)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})

@router.post("/test")
def connection_test(body: dict):
    try:
        return test_connection(body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})

@router.post("/models")
def available_models(body: dict):
    try:
        return list_models(body.get("kind", "llm"), body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})

@router.post("/capability")
def model_capability(body: dict):
    """向量模型能力（支持维度、默认维度、是否可调整维度）；没有收录时明确说不知道。"""
    try:
        return embedding_capability(body.get("kind", "embedding"), body)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})
