"""资料上传与列表路由（契约 ``uploadDocument`` / ``listDocuments``）——只做协议转换。

授权用 C03 的 ``course_teacher``（访问矩阵：匿名 401、非成员 403 COURSE_FORBIDDEN、
学生成员 403 ROLE_FORBIDDEN）。业务规则在 ``app.services.materials``。
"""

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.schemas.errors import Error
from app.schemas.materials import Document, UploadAccepted
from app.services.access import CourseAccess
from app.services.file_storage import FileStorageError, iter_file
from app.services.materials import list_course_materials, upload_material

router = APIRouter(prefix="/api/v1/courses/{cid}/documents", tags=["documents"])

_STATUS_BY_CODE = {
    "UNSUPPORTED_FORMAT": 415,
    "FILE_TOO_LARGE": 413,
    "VALIDATION_ERROR": 422,
    "STORAGE_UNAVAILABLE": 503,
}

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
    responses={
        **_ACCESS_RESPONSES,
        413: {"model": Error, "description": "文件超出上限（`FILE_TOO_LARGE`）"},
        415: {"model": Error, "description": "不支持的资料格式（`UNSUPPORTED_FORMAT`）"},
        422: {"model": Error, "description": "请求体校验失败（`VALIDATION_ERROR`）"},
        503: {"model": Error, "description": "资料存储暂不可用（`STORAGE_UNAVAILABLE`）"},
    },
)
def upload_document(
    request: Request,
    access: CourseAccess = Depends(course_teacher),
    file: UploadFile = File(...),
) -> UploadAccepted | JSONResponse:
    try:
        result = upload_material(
            request.app.state.settings,
            course_id=access.course.id,
            filename=file.filename,
            content_type=file.content_type,
            chunks=iter_file(file.file),
        )
    except FileStorageError as error:
        return _storage_error(error)
    return UploadAccepted(task_id=result.task_id, document_id=result.document_id)
