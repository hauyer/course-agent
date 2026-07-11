from datetime import datetime
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
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskOverviewResponse,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.auth_service import get_current_user
from app.services.course_service import get_course_by_id
from app.services.task_service import (
    create_task,
    delete_task,
    get_task_by_id,
    get_task_overview,
    list_tasks,
    update_task,
    update_task_status,
)


router = APIRouter()


def _check_course_permission(
    *,
    db: Session,
    user_id: int,
    course_id: int | None,
) -> None:
    """任务绑定课程前，验证课程归属。"""
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


def _check_parent_task(
    *,
    db: Session,
    user_id: int,
    parent_task_id: int | None,
    current_task_id: int | None = None,
) -> None:
    """验证父任务属于当前用户。"""
    if parent_task_id is None:
        return

    if current_task_id == parent_task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务不能将自己设置为父任务",
        )

    parent_task = get_task_by_id(
        db=db,
        user_id=user_id,
        task_id=parent_task_id,
    )

    if parent_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="父任务不存在或无权限访问",
        )


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建待办任务",
)
def create_task_api(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_course_permission(
        db=db,
        user_id=current_user.id,
        course_id=task_in.course_id,
    )

    _check_parent_task(
        db=db,
        user_id=current_user.id,
        parent_task_id=task_in.parent_task_id,
    )

    return create_task(
        db=db,
        user_id=current_user.id,
        task_in=task_in,
    )


@router.get(
    "",
    response_model=TaskListResponse,
    summary="查询待办任务列表",
)
def list_tasks_api(
    course_id: int | None = Query(default=None, ge=1),
    task_status: Literal[
        "pending",
        "in_progress",
        "completed",
        "cancelled",
    ] | None = Query(default=None, alias="status"),
    priority: Literal[
        "low",
        "medium",
        "high",
        "urgent",
    ] | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
    due_after: datetime | None = Query(default=None),
    parent_task_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if course_id is not None:
        _check_course_permission(
            db=db,
            user_id=current_user.id,
            course_id=course_id,
        )

    total, items = list_tasks(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        status=task_status,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        parent_task_id=parent_task_id,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "items": items,
    }


# 必须放在 /{task_id} 之前
@router.get(
    "/overview",
    response_model=TaskOverviewResponse,
    summary="获取任务统计",
)
def task_overview_api(
    course_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if course_id is not None:
        _check_course_permission(
            db=db,
            user_id=current_user.id,
            course_id=course_id,
        )

    return get_task_overview(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="获取任务详情",
)
def get_task_api(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_by_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权限访问",
        )

    return task


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    summary="修改任务",
)
def update_task_api(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_by_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权限访问",
        )

    update_data = task_in.model_dump(
        exclude_unset=True
    )

    if "course_id" in update_data:
        _check_course_permission(
            db=db,
            user_id=current_user.id,
            course_id=update_data["course_id"],
        )

    if "parent_task_id" in update_data:
        _check_parent_task(
            db=db,
            user_id=current_user.id,
            parent_task_id=update_data["parent_task_id"],
            current_task_id=task.id,
        )

    try:
        return update_task(
            db=db,
            task=task,
            task_in=task_in,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    summary="修改任务状态",
)
def update_task_status_api(
    task_id: int,
    status_in: TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_by_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权限访问",
        )

    try:
        return update_task_status(
            db=db,
            task=task,
            new_status=status_in.status,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{task_id}",
    summary="删除任务",
)
def delete_task_api(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_task_by_id(
        db=db,
        user_id=current_user.id,
        task_id=task_id,
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在或无权限访问",
        )

    delete_task(
        db=db,
        task=task,
    )

    return {
        "message": "任务删除成功"
    }