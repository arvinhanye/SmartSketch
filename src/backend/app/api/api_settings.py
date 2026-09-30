"""Teacher-only portable API configuration adapters."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.api.dependencies import teacher_account
from app.services.api_settings import public_config, save_for_active_space, test_connection, list_models

router = APIRouter(prefix="/api/v1/api-settings", tags=["api-settings"], dependencies=[Depends(teacher_account)])

@router.get("")
def get_settings(request: Request):
    settings = request.app.state.settings
    return public_config() | {"active": {"LLM_MODE": settings.LLM_MODE, "EMBEDDING_MODE": settings.EMBEDDING_MODE, "EMBEDDING_MODEL": settings.EMBEDDING_MODEL}}

@router.put("")
def put_settings(body: dict, request: Request):
    try:
        return save_for_active_space(body, request.app.state.settings) | {"message": "已保存，请重启智绘学途使设置生效。"}
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
