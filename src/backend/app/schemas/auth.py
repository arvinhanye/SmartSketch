"""Login DTOs mirroring ``LoginRequest``/``LoginResponse``/``User`` in src/contracts/api.v1.yaml.

Declared by hand until the generated DTO package is importable from the backend. The length
caps come from specs/identity-access.md §1.1 (username 3–32) and §1.4 (password 8–128); only
the upper bounds are enforced here, so short or malformed input still gets the uniform 401.
"""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from app.services.auth import PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH


class LoginRequest(BaseModel):
    username: str = Field(max_length=USERNAME_MAX_LENGTH)
    # SecretStr masks the value in repr, validation errors and logs
    password: SecretStr = Field(max_length=PASSWORD_MAX_LENGTH)


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
