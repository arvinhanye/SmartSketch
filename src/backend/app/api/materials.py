"""C07 document list and upload protocol adapters."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.api.dependencies import course_reader, course_teacher
from app.schemas.errors import Error
from app.services.file_storage import FileStorageError
from app.services.materials import MaterialCreationError, list_course_materials, upload_material
from src.contracts.v1.generated.python.models import Document, UploadAccepted


router = APIRouter(prefix="/api/v1/courses/{cid}/documents", tags=["documents"])

_FILE_STATUS = {
    "UNSUPPORTED_FORMAT": 415,
    "FILE_TOO_LARGE": 413,
    "VALIDATION_ERROR": 422,
    "STORAGE_UNAVAILABLE": 503,
}
_MULTIPART_OVERHEAD_BYTES = 16 * 1024


class _BodyTooLarge(Exception):
    pass


def _too_large(limit_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "code": "FILE_TOO_LARGE",
            "message": f"文件超过上限 {limit_bytes} 字节",
            "details": {"limit_bytes": limit_bytes},
        },
    )


def _invalid_file() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": "上传文件字段无效"},
    )


@router.get("", operation_id="listDocuments", response_model=list[Document])
def list_documents(cid: str, request: Request, _access=Depends(course_reader)) -> list[Document]:
    records = list_course_materials(request.app.state.settings, course_id=cid)
    return [
        Document(
            id=row.id, course_id=row.course_id, filename=row.filename,
            format=row.format, size_bytes=row.size_bytes,
            parse_status=row.parse_status, uploaded_at=row.uploaded_at,
        )
        for row in records
    ]


@router.post(
    "", operation_id="uploadDocument", status_code=202, response_model=UploadAccepted,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    },
                },
            },
        },
    },
    responses={
        401: {"model": Error}, 403: {"model": Error}, 413: {"model": Error},
        415: {"model": Error}, 422: {"model": Error}, 500: {"model": Error},
        503: {"model": Error},
    },
)
async def upload_document(
    cid: str, request: Request, _access=Depends(course_teacher),
) -> UploadAccepted | JSONResponse:
    # No File/Form parameter: FastAPI would parse and spool the whole body before
    # course_teacher runs. Authorize first, then cap bytes while Starlette parses.
    settings = request.app.state.settings
    max_body_bytes = settings.UPLOAD_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES
    length = request.headers.get("content-length")
    if length is not None and length.isdecimal() and int(length) > max_body_bytes:
        return _too_large(settings.UPLOAD_MAX_BYTES)

    received = 0

    async def limited_receive():
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > max_body_bytes:
                raise _BodyTooLarge()
        return message

    bounded_request = Request(request.scope, receive=limited_receive)
    try:
        form = await bounded_request.form(max_files=1, max_fields=8)
    except _BodyTooLarge:
        return _too_large(settings.UPLOAD_MAX_BYTES)
    except HTTPException:
        return _invalid_file()

    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            return _invalid_file()
        result = await run_in_threadpool(
            upload_material,
            settings,
            course_id=cid,
            filename=file.filename,
            content_type=file.content_type,
            stream=file.file,
        )
    except FileStorageError as error:
        return JSONResponse(
            status_code=_FILE_STATUS.get(error.code, 500),
            content={"code": error.code, "message": error.message, "details": error.details},
        )
    except MaterialCreationError:
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "无法创建资料处理任务"},
        )
    finally:
        await form.close()
    return UploadAccepted(task_id=result.task.id, document_id=result.material.id)
