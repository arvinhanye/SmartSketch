"""C15 course member HTTP adapters (listMembers, addMember, removeMember).

Protocol conversion only: access is the ``course_teacher`` dependency (§4.1), the §3.3
rules live in ``app.services.members``.
"""

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import course_teacher
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.members import (
    CourseMember,
    MemberAdd,
    add_student_member,
    list_course_members,
    remove_student_member,
)


router = APIRouter(prefix="/api/v1/courses/{cid}/members", tags=["courses"])


@router.get(
    "", operation_id="listMembers", response_model=list[CourseMember],
    responses={401: {"model": Error}, 403: {"model": Error}},
)
def list_members(
    request: Request, access: CourseAccess = Depends(course_teacher)
) -> list[CourseMember]:
    return list_course_members(request.app.state.settings.SQLITE_URL, access.course.id)


@router.post(
    "", operation_id="addMember", response_model=CourseMember, status_code=201,
    responses={
        200: {"model": CourseMember, "description": "已是成员，原角色不变"},
        401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error},
        422: {"model": Error},
    },
)
def add_member(
    body: MemberAdd, request: Request, response: Response,
    access: CourseAccess = Depends(course_teacher),
) -> CourseMember:
    result = add_student_member(
        request.app.state.settings.SQLITE_URL, access.course.id, access.user, body.username
    )
    if not result.created:
        response.status_code = 200
    return result.member


@router.delete(
    "/{uid}", operation_id="removeMember", status_code=204, response_class=Response,
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
def remove_member(
    uid: str, request: Request, access: CourseAccess = Depends(course_teacher)
) -> Response:
    remove_student_member(request.app.state.settings.SQLITE_URL, access.course.id, uid)
    return Response(status_code=204)
