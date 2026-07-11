from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.study_plan import (
    StudyPlanCreate,
    StudyPlanListResponse,
    StudyPlanProgressResponse,
    StudyPlanResponse,
    StudyPlanStatusUpdate,
    StudyPlanTaskCreate,
    StudyPlanTaskListResponse,
    StudyPlanTaskResponse,
    StudyPlanUpdate,
)
from app.services.auth_service import get_current_user
from app.services.course_service import get_course_by_id
from app.services.study_plan_service import (
    create_study_plan,
    create_study_plan_task,
    delete_study_plan,
    delete_study_plan_task,
    get_study_plan_by_id,
    get_study_plan_progress,
    list_study_plan_tasks,
    list_study_plans,
    update_study_plan,
    update_study_plan_status,
)
from app.services.task_service import get_task_by_id


router = APIRouter()


def _check_course_permission(
    *,
    db: Session,
    user_id: int,
    course_id: int | None,
) -> None:
    if course_id is None:
        return

    course = get_course_by_id(
        db=db,
        user_id=user_id,
        course_id=course_id,
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问",
        )


def _get_owned_plan(
    *,
    db: Session,
    user_id: int,
    plan_id: int,
):
    plan = get_study_plan_by_id(
        db=db,
        user_id=user_id,
        plan_id=plan_id,
    )

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="学习计划不存在或无权限访问",
        )

    return plan


@router.post(
    "",
    response_model=StudyPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建学习计划",
)
def create_study_plan_api(
    plan_in: StudyPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_course_permission(
        db=db,
        user_id=current_user.id,
        course_id=plan_in.course_id,
    )

    try:
        return create_study_plan(
            db=db,
            user_id=current_user.id,
            plan_in=plan_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=StudyPlanListResponse,
    summary="查询学习计划列表",
)
def list_study_plans_api(
    course_id: int | None = Query(
        default=None,
        ge=1,
    ),
    plan_status: Literal[
        "draft",
        "active",
        "completed",
        "cancelled",
    ] | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if course_id is not None:
        _check_course_permission(
            db=db,
            user_id=current_user.id,
            course_id=course_id,
        )

    total, items = list_study_plans(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        status=plan_status,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "items": items,
    }


@router.get(
    "/{plan_id}",
    response_model=StudyPlanResponse,
    summary="获取学习计划详情",
)
def get_study_plan_api(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )


@router.put(
    "/{plan_id}",
    response_model=StudyPlanResponse,
    summary="修改学习计划",
)
def update_study_plan_api(
    plan_id: int,
    plan_in: StudyPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    update_data = plan_in.model_dump(
        exclude_unset=True
    )

    if "course_id" in update_data:
        _check_course_permission(
            db=db,
            user_id=current_user.id,
            course_id=update_data["course_id"],
        )

    try:
        return update_study_plan(
            db=db,
            plan=plan,
            plan_in=plan_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{plan_id}/status",
    response_model=StudyPlanResponse,
    summary="修改学习计划状态",
)
def update_study_plan_status_api(
    plan_id: int,
    status_in: StudyPlanStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    try:
        return update_study_plan_status(
            db=db,
            plan=plan,
            new_status=status_in.status,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{plan_id}/tasks",
    response_model=StudyPlanTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="向学习计划添加任务",
)
def create_study_plan_task_api(
    plan_id: int,
    task_in: StudyPlanTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    if task_in.parent_task_id is not None:
        parent_task = get_task_by_id(
            db=db,
            user_id=current_user.id,
            task_id=task_in.parent_task_id,
        )

        if parent_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="父任务不存在或无权限访问",
            )

    try:
        return create_study_plan_task(
            db=db,
            plan=plan,
            user_id=current_user.id,
            task_in=task_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{plan_id}/tasks",
    response_model=StudyPlanTaskListResponse,
    summary="查询学习计划中的任务",
)
def list_study_plan_tasks_api(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    items = list_study_plan_tasks(
        db=db,
        plan_id=plan.id,
    )

    return {
        "total": len(items),
        "items": items,
    }


@router.get(
    "/{plan_id}/progress",
    response_model=StudyPlanProgressResponse,
    summary="查询学习计划进度",
)
def get_study_plan_progress_api(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    return get_study_plan_progress(
        db=db,
        plan_id=plan.id,
    )


@router.delete(
    "/{plan_id}/tasks/{task_id}",
    summary="移除学习计划中的任务",
)
def delete_study_plan_task_api(
    plan_id: int,
    task_id: int,
    delete_task_record: bool = Query(
        default=True,
        description="是否同时删除 tasks 表中的任务",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    deleted = delete_study_plan_task(
        db=db,
        plan_id=plan.id,
        task_id=task_id,
        delete_task=delete_task_record,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="计划任务不存在",
        )

    return {
        "message": "计划任务移除成功"
    }


@router.delete(
    "/{plan_id}",
    summary="删除学习计划",
)
def delete_study_plan_api(
    plan_id: int,
    delete_tasks: bool = Query(
        default=True,
        description="是否同时删除计划生成的任务",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _get_owned_plan(
        db=db,
        user_id=current_user.id,
        plan_id=plan_id,
    )

    delete_study_plan(
        db=db,
        plan=plan,
        delete_tasks=delete_tasks,
    )

    return {
        "message": "学习计划删除成功"
    }