"""Teacher-only cancelled-task resume; lifecycle decisions live in the service."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import task_teacher
from app.api.tasks import TaskSnapshotBody
from app.schemas.errors import Error
from app.schemas.contracts import ModelConfigRequiredError, TaskNotResumableError
from app.services.access import CourseAccess, not_found
from app.services.credentials import ModelConfigRequired
from app.services.task_cancel import TaskNotFound
from app.services.task_events import task_body
from app.services.task_resume import TaskNotResumable, resume_task

router = APIRouter(prefix='/api/v1/tasks', tags=['tasks'])


@router.post('/{tid}/resume', operation_id='resumeTask', summary='继续已取消的任务（教师）',
    response_model=TaskSnapshotBody, response_model_exclude_none=True,
    responses={401: {'model': Error}, 403: {'model': Error}, 404: {'model': Error},
               409: {'model': TaskNotResumableError | ModelConfigRequiredError}})
def resume(tid: str, request: Request, access: CourseAccess = Depends(task_teacher)):
    try:
        task = resume_task(request.app.state.settings, tid, course_id=access.course.id, user_id=access.user.id)
    except TaskNotFound:
        raise not_found() from None
    except TaskNotResumable as error:
        messages = {
            'not_cancelled': '任务尚未取消完成或已继续处理，请刷新状态',
            'worker_active': '任务仍在收尾，请稍后继续处理',
            'artifacts_missing': '任务保存的资料或处理结果不可用，请重新上传',
            'model_config_changed': '模型或思考设置已改变，请恢复原设置后继续处理',
        }
        body = TaskNotResumableError(code='TASK_NOT_RESUMABLE', message=messages[error.reason],
                                    details=dict(stage=error.stage, reason=error.reason))
        return JSONResponse(status_code=409, content=body.model_dump(mode='json', exclude_none=True))
    except ModelConfigRequired:
        body = ModelConfigRequiredError(message='请先在「模型 API 设置」中保存可用的模型 API 配置')
        return JSONResponse(status_code=409, content=body.model_dump(mode='json', exclude_none=True))
    return TaskSnapshotBody.model_validate(task_body(task))
