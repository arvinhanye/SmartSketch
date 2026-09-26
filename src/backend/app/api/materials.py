"""资料上传、列表、删除与上传策略路由（契约 ``uploadDocument`` / ``listDocuments`` /
``deleteDocument`` / ``getUploadPolicy``）——只做协议转换。

授权用 C03 的 ``course_teacher``（访问矩阵：匿名 401、非成员 403 COURSE_FORBIDDEN、
学生成员 403 ROLE_FORBIDDEN）。业务规则在 ``app.services.materials``。

上传路由不声明 ``File``/``UploadFile`` 参数：否则 FastAPI 会在执行 ``course_teacher``
之前解析并暂存整个 multipart 请求体。这里先授权，再按 ``Content-Length`` 与实收字节
双重计数有界解析表单（ADR-019；做法移植自 539210 的 #229）。
"""

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Message

from app.api.dependencies import course_teacher
from app.schemas.errors import Error
from app.schemas.materials import Document, DocumentNotDeletableDetails, UploadAccepted, UploadPolicy
from app.services.access import CourseAccess, not_found
from app.services.file_storage import FileStorageError, FileTooLargeError, iter_file
from app.services.materials import (
    MaterialNotDeletable,
    delete_course_material,
    list_course_materials,
    upload_material,
)

router = APIRouter(prefix="/api/v1/courses/{cid}/documents", tags=["documents"])
# ADR-022：上传策略与资料同属 documents 标签，但路径不在 /documents 之下。
policy_router = APIRouter(prefix="/api/v1/courses/{cid}", tags=["documents"])

_STATUS_BY_CODE = {
    "UNSUPPORTED_FORMAT": 415,
    "FILE_TOO_LARGE": 413,
    "VALIDATION_ERROR": 422,
    "STORAGE_UNAVAILABLE": 503,
}

# multipart 分隔符、各部分头部与少量普通字段的余量。文件本身的上限仍由 C05
# ``FileStorage`` 按 ``UPLOAD_MAX_BYTES`` 精确校验；这里只防止授权通过后仍接收远超
# 上限的请求体。16 KiB 足够覆盖合法请求的表单开销（含 255 字符文件名）。
MULTIPART_OVERHEAD_BYTES = 16 * 1024
# 契约只有一个 ``file`` 字段；给普通字段留少量余地，其余视为无效请求。
_MAX_FORM_FILES = 1
_MAX_FORM_FIELDS = 8

_ACCESS_RESPONSES = {
    401: {"model": Error, "description": "未认证或令牌失效"},
    403: {"model": Error, "description": "角色不允许，或跨课程访问（`COURSE_FORBIDDEN`）"},
}


def _storage_error(error: FileStorageError) -> JSONResponse:
    details = error.details or None
    if error.code == "VALIDATION_ERROR":
        # 与全局校验处理器同形：details.fields 为 [{in, field, reason}]，不回显文件名。
        reasons = error.details.get("fields", {})
        details = {
            "fields": [
                {"in": "body", "field": field, "reason": str(reason)}
                for field, reason in reasons.items()
            ]
        }
    body = Error(code=error.code, message=error.message, details=details)
    return JSONResponse(
        status_code=_STATUS_BY_CODE.get(error.code, 500),
        content=body.model_dump(exclude_none=True),
    )


@router.get(
    "",
    operation_id="listDocuments",
    summary="课程资料列表",
    response_model=list[Document],
    responses=_ACCESS_RESPONSES,
)
def list_documents(
    request: Request, access: CourseAccess = Depends(course_teacher)
) -> list[Document]:
    records = list_course_materials(request.app.state.settings, access.course.id)
    return [
        Document(
            id=record.id,
            course_id=record.course_id,
            filename=record.filename,
            format=record.format,
            size_bytes=record.size_bytes,
            parse_status=record.parse_status,
            task_id=record.task_id,
            uploaded_at=record.uploaded_at,
        )
        for record in records
    ]


@router.post(
    "",
    operation_id="uploadDocument",
    summary="上传资料并创建图谱生成任务（教师）",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAccepted,
    # 路由不声明 UploadFile 参数，请求体结构按契约手工写入 OpenAPI。
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
        **_ACCESS_RESPONSES,
        413: {"model": Error, "description": "文件超出上限（`FILE_TOO_LARGE`）"},
        415: {"model": Error, "description": "不支持的资料格式（`UNSUPPORTED_FORMAT`）"},
        422: {"model": Error, "description": "请求体校验失败（`VALIDATION_ERROR`）"},
        503: {"model": Error, "description": "资料存储暂不可用（`STORAGE_UNAVAILABLE`）"},
    },
)
async def upload_document(
    request: Request,
    access: CourseAccess = Depends(course_teacher),
) -> UploadAccepted | JSONResponse:
    settings = request.app.state.settings
    try:
        form = await _read_bounded_form(request, settings.UPLOAD_MAX_BYTES)
    except _BodyTooLarge:
        return _storage_error(FileTooLargeError(settings.UPLOAD_MAX_BYTES))
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise _invalid_body("file", "missing")
        result = await run_in_threadpool(
            upload_material,
            settings,
            course_id=access.course.id,
            filename=file.filename,
            content_type=file.content_type,
            chunks=iter_file(file.file),
        )
    except FileStorageError as error:
        return _storage_error(error)
    finally:
        await form.close()
    return UploadAccepted(task_id=result.task_id, document_id=result.document_id)


@router.delete(
    "/{did}",
    operation_id="deleteDocument",
    summary="删除未产生图谱贡献的资料（教师）",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={
        **_ACCESS_RESPONSES,
        404: {"model": Error, "description": "资料不存在，或不属于该课程（`NOT_FOUND`）"},
        409: {"model": Error, "description": "资料仍在处理、已产生图谱贡献或清理未完成（`DOCUMENT_NOT_DELETABLE`）"},
    },
)
def delete_document(
    did: str, request: Request, access: CourseAccess = Depends(course_teacher)
) -> Response:
    outcome = delete_course_material(
        request.app.state.settings, course_id=access.course.id, material_id=did
    )
    if outcome is None:
        raise not_found()
    if isinstance(outcome, MaterialNotDeletable):
        details = DocumentNotDeletableDetails(stage=outcome.stage, reason=outcome.reason)
        body = Error(
            code="DOCUMENT_NOT_DELETABLE",
            message="资料仍在处理或已进入图谱，不能删除",
            details=details.model_dump(),
        )
        return JSONResponse(status_code=409, content=body.model_dump(exclude_none=True))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class _BodyTooLarge(Exception):
    """请求体超过 ``UPLOAD_MAX_BYTES`` + 表单开销；路由转为 413 ``FILE_TOO_LARGE``。"""


def _invalid_body(field: str, reason: str) -> RequestValidationError:
    # 交给全局校验处理器，输出与其他 422 同形的 details.fields。
    return RequestValidationError([{"type": reason, "loc": ("body", field), "msg": reason}])


async def _read_bounded_form(request: Request, max_file_bytes: int) -> FormData:
    """授权之后调用：请求体超过 ``max_file_bytes`` + 表单开销即停止接收，抛 ``_BodyTooLarge``。"""
    max_body_bytes = max_file_bytes + MULTIPART_OVERHEAD_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdecimal() and int(declared) > max_body_bytes:
        raise _BodyTooLarge
    # Content-Length 可能缺失（分块传输）或不实，按实际收到的字节再计一次。
    received = 0

    async def counting_receive() -> Message:
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > max_body_bytes:
                raise _BodyTooLarge
        return message

    bounded = Request(request.scope, receive=counting_receive)
    try:
        return await bounded.form(max_files=_MAX_FORM_FILES, max_fields=_MAX_FORM_FIELDS)
    except StarletteHTTPException:
        # 表单格式错误或字段/文件数超限。
        raise _invalid_body("file", "multipart_invalid") from None


@policy_router.get(
    "/upload-policy",
    operation_id="getUploadPolicy",
    response_model=UploadPolicy,
    responses=_ACCESS_RESPONSES,
)
def get_upload_policy(request: Request, access: CourseAccess = Depends(course_teacher)) -> UploadPolicy:
    """ADR-022：返回服务端当前的 ``UPLOAD_MAX_BYTES``，与 413 的 ``limit_bytes`` 同源。"""
    return UploadPolicy(max_bytes=request.app.state.settings.UPLOAD_MAX_BYTES)
