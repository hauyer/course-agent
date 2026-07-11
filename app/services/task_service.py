from datetime import datetime, timezone

from sqlalchemy import case
from sqlalchemy.orm import Query, Session

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


VALID_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "cancelled",
}


def get_task_by_id(
    db: Session,
    *,
    user_id: int,
    task_id: int,
) -> Task | None:
    """获取当前用户拥有的任务。"""
    return (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.user_id == user_id,
        )
        .first()
    )


def create_task(
    db: Session,
    *,
    user_id: int,
    task_in: TaskCreate,
) -> Task:
    """创建待办任务。"""
    task = Task(
        user_id=user_id,
        course_id=task_in.course_id,
        parent_task_id=task_in.parent_task_id,
        title=task_in.title.strip(),
        description=task_in.description,
        status="pending",
        priority=task_in.priority,
        due_at=task_in.due_at,
        estimated_minutes=task_in.estimated_minutes,
        source=task_in.source,
    )

    db.add(task)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    parent_task_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[Task]]:
    """按条件查询当前用户的任务。"""
    query: Query = db.query(Task).filter(
        Task.user_id == user_id
    )

    if course_id is not None:
        query = query.filter(Task.course_id == course_id)

    if status is not None:
        query = query.filter(Task.status == status)

    if priority is not None:
        query = query.filter(Task.priority == priority)

    if due_before is not None:
        query = query.filter(Task.due_at <= due_before)

    if due_after is not None:
        query = query.filter(Task.due_at >= due_after)

    if parent_task_id is not None:
        query = query.filter(
            Task.parent_task_id == parent_task_id
        )

    total = query.count()

    # 未完成任务在前，有截止日期的在前
    items = (
        query.order_by(
            case(
                (Task.status == "completed", 1),
                (Task.status == "cancelled", 2),
                else_=0,
            ),
            case(
                (Task.due_at.is_(None), 1),
                else_=0,
            ),
            Task.due_at.asc(),
            Task.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return total, items


def _apply_status(
    task: Task,
    new_status: str,
) -> None:
    if new_status not in VALID_STATUSES:
        raise ValueError("非法任务状态")

    task.status = new_status

    if new_status == "completed":
        task.completed_at = datetime.now(timezone.utc)
    else:
        task.completed_at = None


def update_task(
    db: Session,
    *,
    task: Task,
    task_in: TaskUpdate,
) -> Task:
    """修改任务内容。"""
    update_data = task_in.model_dump(
        exclude_unset=True
    )

    if "title" in update_data:
        if update_data["title"] is None:
            raise ValueError("任务标题不能为空")

        update_data["title"] = update_data["title"].strip()

        if not update_data["title"]:
            raise ValueError("任务标题不能为空")

    new_status = update_data.pop("status", None)

    for field_name, value in update_data.items():
        setattr(task, field_name, value)

    if new_status is not None:
        _apply_status(task, new_status)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(task)
    return task


def update_task_status(
    db: Session,
    *,
    task: Task,
    new_status: str,
) -> Task:
    """单独更新任务状态。"""
    _apply_status(task, new_status)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(task)
    return task


def delete_task(
    db: Session,
    *,
    task: Task,
) -> None:
    """删除任务。"""
    try:
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()
        raise


def get_task_overview(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
) -> dict[str, int]:
    """获取任务状态统计。"""
    base_query: Query = db.query(Task).filter(
        Task.user_id == user_id
    )

    if course_id is not None:
        base_query = base_query.filter(
            Task.course_id == course_id
        )

    now = datetime.now(timezone.utc)

    total = base_query.count()

    pending = base_query.filter(
        Task.status == "pending"
    ).count()

    in_progress = base_query.filter(
        Task.status == "in_progress"
    ).count()

    completed = base_query.filter(
        Task.status == "completed"
    ).count()

    cancelled = base_query.filter(
        Task.status == "cancelled"
    ).count()

    overdue = base_query.filter(
        Task.status.in_(["pending", "in_progress"]),
        Task.due_at.isnot(None),
        Task.due_at < now,
    ).count()

    return {
        "total": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "cancelled": cancelled,
        "overdue": overdue,
    }