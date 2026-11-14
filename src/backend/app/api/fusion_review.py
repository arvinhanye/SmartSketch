"""Teacher-only disambiguation coverage, automatic merge history and safe undo."""
from __future__ import annotations

from dataclasses import asdict
import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import course_teacher
from app.api.graph_nodes import _context, _error
from app.repositories.fusion import StaleFusionPlan
from app.repositories.neo4j import RepositoryError
from app.repositories.task_leases import LeaseLost
from app.schemas.contracts import DisambiguationCoverage, FusionMergeHistory, FusionUndoResult
from app.schemas.errors import Error
from app.services.access import CourseAccess, course_forbidden, not_found
from app.services.fusion import undo
from app.services.fusion.review import InvalidHistoryCursor, read_merge_history
from app.services.graph.review import read_queue

router=APIRouter(prefix='/api/v1/courses/{cid}/review',tags=['review'])
_ERRORS={n:{'model':Error} for n in (401,403,404,409,422,503)}


def fusion_context(request: Request) -> undo.UndoContext:
    context=getattr(request.app.state,'fusion_context',None)
    if context is None:
        context=undo.UndoContext.from_settings(request.app.state.settings,
            repository=getattr(request.app.state,'fusion_repository',None))
        request.app.state.fusion_context=context
    return context


def _run(operation):
    try:
        return operation()
    except (RepositoryError,sqlite3.Error):
        return _error(503,'STORAGE_UNAVAILABLE','存储暂不可用，请稍后重试')
    except undo.UndoBusy:
        return _error(409,'COURSE_BUSY','课程正在处理其他修改，请稍后重试')
    except (StaleFusionPlan,LeaseLost):
        return _error(409,'REVISION_CONFLICT','草稿已变化或操作租约失效，请重新读取后预览',
                      {'reason':'snapshot_changed'})
    except PermissionError:
        raise course_forbidden() from None
    except LookupError:
        raise not_found() from None


@router.get('/disambiguation',operation_id='getDisambiguationCoverage',response_model=DisambiguationCoverage,
            responses={k:v for k,v in _ERRORS.items() if k in (401,403,422,503)})
def get_disambiguation_coverage(request: Request,access: CourseAccess=Depends(course_teacher)):
    return _run(lambda: JSONResponse(content=read_queue(_context(request,access),access.course.id)['disambiguation']))


@router.get('/merges',operation_id='listAutomaticMerges',response_model=FusionMergeHistory,
            responses={k:v for k,v in _ERRORS.items() if k in (401,403,422,503)})
def list_automatic_merges(request: Request,cursor: str | None=Query(None,min_length=1,max_length=1024),
                         limit: int=Query(50,ge=1,le=200),access: CourseAccess=Depends(course_teacher)):
    def operation():
        try:
            body=read_merge_history(request.app.state.settings.SQLITE_URL,access.course.id,cursor=cursor,limit=limit)
        except InvalidHistoryCursor:
            raise RequestValidationError([{'type':'invalid_cursor','loc':('query','cursor')}]) from None
        return JSONResponse(content=body)
    return _run(operation)


def _revision(body: object) -> int:
    if not isinstance(body,dict):
        raise RequestValidationError([{'type':'model_attributes_type','loc':('body',)}])
    errors=[{'type':'extra_forbidden','loc':('body',key)} for key in body if key!='expected_revision']
    value=body.get('expected_revision')
    if 'expected_revision' not in body:
        errors.append({'type':'missing','loc':('body','expected_revision')})
    elif type(value) is not int or value<0:
        errors.append({'type':'int_type' if type(value) is not int else 'greater_than_equal',
                       'loc':('body','expected_revision')})
    if errors: raise RequestValidationError(errors)
    return value


def _undo(request,access,plan_id,group_id,body,*,apply):
    revision=_revision(body)
    def operation():
        context=fusion_context(request)
        result=(undo.undo_merge if apply else undo.preview_undo)(sqlite_url=context.sqlite_url,
            repo=context.repo,course_id=access.course.id,actor_id=access.user.id,
            plan_id=plan_id,group_id=group_id,expected_revision=revision,
            lock_seconds=context.lock_seconds,wait_seconds=context.wait_seconds)
        data={k:v for k,v in asdict(result).items() if k!='storage_version_id'}
        data.update(plan_id=plan_id,changed=result.status=='undone')
        data=FusionUndoResult.model_validate(data).model_dump(mode='json',exclude_none=True)
        if apply and result.status=='conflict':
            return _error(409,'REVISION_CONFLICT','相关内容已变化，未撤销，请查看冲突并重新预览',data)
        return JSONResponse(content=data)
    return _run(operation)


@router.post('/merges/{plan_id}/{group_id}/undo-preview',operation_id='previewAutomaticMergeUndo',
             response_model=FusionUndoResult,responses=_ERRORS)
def preview_automatic_merge_undo(request: Request,plan_id: str=Path(min_length=1,max_length=200),
        group_id: str=Path(min_length=1,max_length=200),body: Any=Body(...),
        access: CourseAccess=Depends(course_teacher)):
    return _undo(request,access,plan_id,group_id,body,apply=False)


@router.post('/merges/{plan_id}/{group_id}/undo',operation_id='undoAutomaticMerge',
             response_model=FusionUndoResult,responses=_ERRORS)
def undo_automatic_merge(request: Request,plan_id: str=Path(min_length=1,max_length=200),
        group_id: str=Path(min_length=1,max_length=200),body: Any=Body(...),
        access: CourseAccess=Depends(course_teacher)):
    return _undo(request,access,plan_id,group_id,body,apply=True)
