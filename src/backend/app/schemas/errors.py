"""The contract ``Error`` body shared by every HTTP error response (src/contracts/errors.v1.md)."""

from typing import Any

from pydantic import BaseModel


class Error(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
