"""POST /api/v1/auth/login — protocol translation only (contract operation ``login``).

Request/response models mirror ``LoginRequest``/``LoginResponse``/``User``/``Error`` in
src/contracts/api.v1.yaml; they are declared here, as health.py does, until the generated
DTO package is importable from the backend.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr

from app.config import SettingsError
from app.services.auth import AuthService, InvalidCredentials, LoginRateLimited


class LoginRequest(BaseModel):
    username: str
    password: SecretStr  # masked in repr, validation errors and logs


class User(BaseModel):
    id: str
    username: str
    role: Literal["teacher", "student"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    # optional in the contract (generated model: Optional[int]); this endpoint always sends it
    expires_in: int | None = Field(default=None, description="秒")
    user: User


class Error(BaseModel):
    code: str
    message: str


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
