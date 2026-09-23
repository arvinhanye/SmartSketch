"""Lightweight process health endpoint."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str = Field(min_length=1)


router = APIRouter(tags=["auth"])


@router.get("/health", response_model=HealthResponse, operation_id="getHealth")
def get_health(request: Request) -> HealthResponse:
    return HealthResponse(status="ok", version=request.app.version)
