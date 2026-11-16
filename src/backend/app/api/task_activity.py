"""Authenticated task activity snapshot, separate from the unchanged v1 SSE frames."""

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import task_teacher
from app.schemas.errors import Error
from app.schemas.task_activity import TaskActivity
from app.services.access import CourseAccess, not_found
from app.services.task_activity import get_activity


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get(
    "/{tid}/activity", operation_id="getTaskActivity", summary="任务处理详情（教师）",
    response_model=TaskActivity,
    responses={
        401: {"model": Error, "description": "未认证或凭据无效"},
        403: {"model": Error, "description": "课程角色不是教师"},
        404: {"model": Error, "description": "任务不存在或不是课程成员"},
    },
)
def read_activity(
    tid: str, request: Request, access: CourseAccess = Depends(task_teacher),
) -> TaskActivity:
    settings = request.app.state.settings
    result = get_activity(settings.SQLITE_URL, tid, course_id=access.course.id,
                          viewer_id=access.user.id, personal=settings.LLM_MODE == "personal",
                          now=request.app.state.auth_clock())
    if result is None:
        raise not_found()
    return result
