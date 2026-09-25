"""C04 list and create course HTTP adapters; business rules live in services."""

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError

from app.api.dependencies import current_user, teacher_account
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import Course, CourseCreate
from app.schemas.errors import Error
from app.services.courses import create_new_course, list_courses


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
