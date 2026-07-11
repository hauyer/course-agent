from datetime import datetime, time

from sqlalchemy.orm import Query, Session

from app.models.study_plan import StudyPlan
from app.models.study_plan_task import StudyPlanTask
from app.models.task import Task
from app.schemas.study_plan import (
    StudyPlanCreate,
    StudyPlanTaskCreate,
    StudyPlanUpdate,
)


VALID_PLAN_STATUSES = {
    "draft",
    "active",
    "completed",
    "cancelled",
}


def get_study_plan_by_id(
    db: Session,
    *,
    user_id: int,
    plan_id: int,
) -> StudyPlan | None:
    """查询当前用户拥有的学习计划。"""
    return (
        db.query(StudyPlan)
        .filter(
            StudyPlan.id == plan_id,
            StudyPlan.user_id == user_id,
        )
        .first()
    )


def create_study_plan(
    db: Session,
    *,
    user_id: int,
    plan_in: StudyPlanCreate,
) -> StudyPlan:
    """创建学习计划。"""
    title = plan_in.title.strip()

    if not title:
        raise ValueError("计划标题不能为空")

    plan = StudyPlan(
        user_id=user_id,
        course_id=plan_in.course_id,
        title=title,
        goal=plan_in.goal,
        start_date=plan_in.start_date,
        end_date=plan_in.end_date,
        daily_minutes=plan_in.daily_minutes,
        status=plan_in.status,
    )

    db.add(plan)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(plan)
    return plan


def list_study_plans(
    db: Session,
    *,
    user_id: int,
    course_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[StudyPlan]]:
    """查询学习计划列表。"""
    query: Query = db.query(StudyPlan).filter(
        StudyPlan.user_id == user_id
    )

    if course_id is not None:
        query = query.filter(
            StudyPlan.course_id == course_id
        )

    if status is not None:
        query = query.filter(
            StudyPlan.status == status
        )

    total = query.count()

    items = (
        query.order_by(
            StudyPlan.updated_at.desc(),
            StudyPlan.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return total, items


def update_study_plan(
    db: Session,
    *,
    plan: StudyPlan,
    plan_in: StudyPlanUpdate,
) -> StudyPlan:
    """修改学习计划。"""
    update_data = plan_in.model_dump(
        exclude_unset=True
    )

    if "title" in update_data:
        title = update_data["title"]

        if title is None or not title.strip():
            raise ValueError("计划标题不能为空")

        update_data["title"] = title.strip()

    new_start_date = update_data.get(
        "start_date",
        plan.start_date,
    )

    new_end_date = update_data.get(
        "end_date",
        plan.end_date,
    )

    if new_end_date < new_start_date:
        raise ValueError("计划结束日期不能早于开始日期")

    if (
        "course_id" in update_data
        and update_data["course_id"] != plan.course_id
    ):
        linked_count = (
            db.query(StudyPlanTask)
            .filter(
                StudyPlanTask.study_plan_id == plan.id
            )
            .count()
        )

        if linked_count > 0:
            raise ValueError(
                "已有任务的学习计划不能直接更换课程"
            )

    out_of_range_count = (
        db.query(StudyPlanTask)
        .filter(
            StudyPlanTask.study_plan_id == plan.id,
            (
                (StudyPlanTask.planned_date < new_start_date)
                |
                (StudyPlanTask.planned_date > new_end_date)
            ),
        )
        .count()
    )

    if out_of_range_count > 0:
        raise ValueError(
            "修改后的日期范围不包含已有计划任务"
        )

    for field_name, value in update_data.items():
        setattr(plan, field_name, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(plan)
    return plan


def update_study_plan_status(
    db: Session,
    *,
    plan: StudyPlan,
    new_status: str,
) -> StudyPlan:
    """修改学习计划状态。"""
    if new_status not in VALID_PLAN_STATUSES:
        raise ValueError("非法的学习计划状态")

    plan.status = new_status

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(plan)
    return plan


def create_study_plan_task(
    db: Session,
    *,
    plan: StudyPlan,
    user_id: int,
    task_in: StudyPlanTaskCreate,
) -> dict:
    """
    创建计划任务。

    tasks 表保存真实任务，
    study_plan_tasks 保存计划关联关系。
    """
    if not (
        plan.start_date
        <= task_in.planned_date
        <= plan.end_date
    ):
        raise ValueError(
            "任务安排日期必须位于学习计划日期范围内"
        )

    title = task_in.title.strip()

    if not title:
        raise ValueError("任务标题不能为空")

    actual_due_time = task_in.due_time or time(
        hour=23,
        minute=59,
        second=59,
    )

    due_at = datetime.combine(
        task_in.planned_date,
        actual_due_time,
    )

    task = Task(
        user_id=user_id,
        course_id=plan.course_id,
        parent_task_id=task_in.parent_task_id,
        title=title,
        description=task_in.description,
        status="pending",
        priority=task_in.priority,
        due_at=due_at,
        estimated_minutes=task_in.estimated_minutes,
        source="study_plan",
        completed_at=None,
    )

    db.add(task)

    try:
        # 先获取任务主键，但暂时不提交
        db.flush()

        link = StudyPlanTask(
            study_plan_id=plan.id,
            task_id=task.id,
            planned_date=task_in.planned_date,
            sequence_no=task_in.sequence_no,
        )

        db.add(link)
        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(task)
    db.refresh(link)

    return {
        "id": link.id,
        "study_plan_id": link.study_plan_id,
        "task_id": link.task_id,
        "planned_date": link.planned_date,
        "sequence_no": link.sequence_no,
        "task": task,
    }


def list_study_plan_tasks(
    db: Session,
    *,
    plan_id: int,
) -> list[dict]:
    """查询学习计划中的全部任务。"""
    rows = (
        db.query(
            StudyPlanTask,
            Task,
        )
        .join(
            Task,
            Task.id == StudyPlanTask.task_id,
        )
        .filter(
            StudyPlanTask.study_plan_id == plan_id
        )
        .order_by(
            StudyPlanTask.planned_date.asc(),
            StudyPlanTask.sequence_no.asc(),
            StudyPlanTask.id.asc(),
        )
        .all()
    )

    return [
        {
            "id": link.id,
            "study_plan_id": link.study_plan_id,
            "task_id": link.task_id,
            "planned_date": link.planned_date,
            "sequence_no": link.sequence_no,
            "task": task,
        }
        for link, task in rows
    ]


def get_study_plan_progress(
    db: Session,
    *,
    plan_id: int,
) -> dict:
    """根据 tasks 表的状态实时计算计划进度。"""
    query: Query = (
        db.query(Task)
        .join(
            StudyPlanTask,
            StudyPlanTask.task_id == Task.id,
        )
        .filter(
            StudyPlanTask.study_plan_id == plan_id
        )
    )

    tasks = query.all()

    total_tasks = len(tasks)

    pending_tasks = sum(
        task.status == "pending"
        for task in tasks
    )

    in_progress_tasks = sum(
        task.status == "in_progress"
        for task in tasks
    )

    completed_tasks = sum(
        task.status == "completed"
        for task in tasks
    )

    cancelled_tasks = sum(
        task.status == "cancelled"
        for task in tasks
    )

    now = datetime.now()

    overdue_tasks = sum(
        task.status in {"pending", "in_progress"}
        and task.due_at is not None
        and task.due_at < now
        for task in tasks
    )

    estimated_total_minutes = sum(
        task.estimated_minutes or 0
        for task in tasks
    )

    completed_estimated_minutes = sum(
        task.estimated_minutes or 0
        for task in tasks
        if task.status == "completed"
    )

    if total_tasks == 0:
        progress_percent = 0.0
    else:
        progress_percent = round(
            completed_tasks / total_tasks * 100,
            2,
        )

    return {
        "study_plan_id": plan_id,
        "total_tasks": total_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "completed_tasks": completed_tasks,
        "cancelled_tasks": cancelled_tasks,
        "overdue_tasks": overdue_tasks,
        "estimated_total_minutes": (
            estimated_total_minutes
        ),
        "completed_estimated_minutes": (
            completed_estimated_minutes
        ),
        "progress_percent": progress_percent,
    }


def delete_study_plan_task(
    db: Session,
    *,
    plan_id: int,
    task_id: int,
    delete_task: bool = True,
) -> bool:
    """移除计划中的任务。"""
    link = (
        db.query(StudyPlanTask)
        .filter(
            StudyPlanTask.study_plan_id == plan_id,
            StudyPlanTask.task_id == task_id,
        )
        .first()
    )

    if link is None:
        return False

    task = db.query(Task).filter(
        Task.id == task_id
    ).first()

    try:
        db.delete(link)

        if delete_task and task is not None:
            db.delete(task)

        db.commit()

    except Exception:
        db.rollback()
        raise

    return True


def delete_study_plan(
    db: Session,
    *,
    plan: StudyPlan,
    delete_tasks: bool = True,
) -> None:
    """删除学习计划。"""
    links = (
        db.query(StudyPlanTask)
        .filter(
            StudyPlanTask.study_plan_id == plan.id
        )
        .all()
    )

    task_ids = [
        link.task_id
        for link in links
    ]

    try:
        for link in links:
            db.delete(link)

        if delete_tasks and task_ids:
            (
                db.query(Task)
                .filter(
                    Task.id.in_(task_ids),
                    Task.user_id == plan.user_id,
                )
                .delete(
                    synchronize_session=False
                )
            )

        db.delete(plan)
        db.commit()

    except Exception:
        db.rollback()
        raise