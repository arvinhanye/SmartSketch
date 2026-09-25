"""POST /api/v1/auth/login — protocol translation only (contract operation ``login``).

Request/response models live in ``app.schemas.auth``; malformed requests are answered by the
application-wide ``VALIDATION_ERROR`` handler registered in ``app.main``.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import SettingsError
from app.schemas.auth import LoginRequest, LoginResponse, User
from app.schemas.errors import Error
from app.services.auth import AuthService, InvalidCredentials, LoginRateLimited

_UNAUTHENTICATED = {"code": "UNAUTHENTICATED", "message": "用户名或口令错误"}
_RATE_LIMITED = {"code": "RATE_LIMITED", "message": "登录失败次数过多，请稍后再试"}
_INTERNAL_ERROR = {"code": "INTERNAL_ERROR", "message": "服务暂时无法登录，请联系管理员"}

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_auth_service(request: Request) -> AuthService | None:
    state = request.app.state
    try:
        return AuthService(state.settings, state.login_limiter, state.auth_clock)
    except SettingsError:
        return None  # only reachable in factory-built apps; the served entry refuses to start


@router.post(
    "/login",
    operation_id="login",
    summary="登录，返回访问令牌与角色",
    response_model=LoginResponse,
    responses={
        401: {"model": Error, "description": "未认证或令牌失效"},
        422: {"model": Error, "description": "请求体校验失败（`VALIDATION_ERROR`）"},
        429: {"model": Error, "description": "请求受限：`RATE_LIMITED`，可按 `Retry-After` 重试"},
    },
)
def login(
    body: LoginRequest, service: AuthService | None = Depends(get_auth_service)
) -> LoginResponse | JSONResponse:
    if service is None:
        return JSONResponse(status_code=500, content=_INTERNAL_ERROR)
    try:
        result = service.login(body.username, body.password.get_secret_value())
    except InvalidCredentials:
        return JSONResponse(status_code=401, content=_UNAUTHENTICATED)
    except LoginRateLimited as limited:
        return JSONResponse(
            status_code=429,
            content=_RATE_LIMITED,
            headers={"Retry-After": str(limited.retry_after)},
        )
    return LoginResponse(
        access_token=result.access_token,
        token_type="bearer",
        expires_in=result.expires_in,
        user=User(id=result.user_id, username=result.username, role=result.role),
    )
