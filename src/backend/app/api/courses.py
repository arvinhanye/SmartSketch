"""C04 list and create course HTTP adapters; business rules live in services."""

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError

from app.api.dependencies import course_reader, current_user, teacher_account
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import Course, CourseCreate
from app.schemas.errors import Error
from app.services.access import CourseAccess
from app.services.courses import course_detail, create_new_course, list_courses


router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


@router.get(
    "", operation_id="listCourses", response_model=list[Course],
    response_model_exclude_none=True,
    responses={401: {"model": Error}},
)
def list_my_courses(
    request: Request, user: AccountRecord = Depends(current_user)
) -> list[Course]:
    return list_courses(request.app.state.settings.SQLITE_URL, user)


@router.post(
    "", operation_id="createCourse", response_model=Course, status_code=201,
    response_model_exclude_none=True,
    responses={401: {"model": Error}, 403: {"model": Error}, 422: {"model": Error}},
)
def create_my_course(
    body: CourseCreate, request: Request,
    user: AccountRecord = Depends(teacher_account),
) -> Course:
    # The generated Python model widens an optional string to Optional[str]; the
    # OpenAPI source permits omission but not an explicit JSON null.
    if "description" in body.model_fields_set and body.description is None:
        raise RequestValidationError([
            {"type": "string_type", "loc": ("body", "description"), "input": None}
        ])
    return create_new_course(
        request.app.state.settings.SQLITE_URL,
        user,
        name=body.name,
        description=body.description,
    )


@router.get(
    "/{cid}", operation_id="getCourse", response_model=Course,
    response_model_exclude_none=True,
    responses={401: {"model": Error}, 403: {"model": Error}, 404: {"model": Error}},
)
def get_my_course(request: Request, access: CourseAccess = Depends(course_reader)) -> Course:
    # course_reader already maps non-members to 403 and students on a never-published
    # course to 404 GRAPH_NOT_PUBLISHED (specs/identity-access.md §4.1).
    return course_detail(request.app.state.settings.SQLITE_URL, access)
