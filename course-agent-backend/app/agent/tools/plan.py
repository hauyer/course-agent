from datetime import date, datetime, time, timedelta

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


def _config_int(config: RunnableConfig | None, key: str, default: int = 0) -> int:
    try:
        return int((config or {}).get("configurable", {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _user_id(config: RunnableConfig | None) -> int:
    value = _config_int(config, "user_id", 0)
    if value < 1:
        raise ValueError("无法确定当前用户")
    return value


def _course_id(course_id: int, config: RunnableConfig | None) -> int | None:
    value = course_id if course_id > 0 else _config_int(config, "course_id", 0)
    return value if value > 0 else None


def _db():
    from app.database import SessionLocal
    return SessionLocal()


@tool
def create_study_plan(
    title: str,
    course_id: int = 0,
    description: str = "",
    start_date: str = "",
    end_date: str = "",
    daily_minutes: int = 60,
    status: str = "active",
    config: RunnableConfig = None,
) -> str:
    """创建学习计划；未指定日期时从今天开始，默认持续 30 天。"""
    from app.schemas.study_plan import StudyPlanCreate
    from app.services.course_service import get_course_by_id
    from app.services.study_plan_service import create_study_plan as create_plan

    db = _db()
    try:
        uid, cid = _user_id(config), _course_id(course_id, config)
        if cid and get_course_by_id(db=db, user_id=uid, course_id=cid) is None:
            return "计划创建失败：课程不存在或无权限"
        start = date.fromisoformat(start_date) if start_date else date.today()
        end = date.fromisoformat(end_date) if end_date else start + timedelta(days=29)
        plan = create_plan(
            db=db,
            user_id=uid,
            plan_in=StudyPlanCreate(
                title=title,
                course_id=cid,
                goal=description or None,
                start_date=start,
                end_date=end,
                daily_minutes=max(1, min(int(daily_minutes), 1440)),
                status=status,
            ),
        )
        return f"学习计划《{plan.title}》创建成功（ID: {plan.id}，{start} 至 {end}）"
    except Exception as exc:
        return f"计划创建失败：{exc}"
    finally:
        db.close()


@tool
def list_study_plans(
    course_id: int = 0,
    status: str = "",
    config: RunnableConfig = None,
) -> str:
    """列出当前用户的学习计划，默认限定当前课程。"""
    from app.services.study_plan_service import list_study_plans as list_plans

    db = _db()
    try:
        total, plans = list_plans(
            db=db,
            user_id=_user_id(config),
            course_id=_course_id(course_id, config),
            status=status or None,
            limit=50,
            offset=0,
        )
        if not plans:
            return "暂无学习计划"
        lines = [f"共 {total} 个计划："]
        lines.extend(
            f"#{plan.id} [{plan.status}] 《{plan.title}》· {plan.start_date} 至 {plan.end_date}"
            for plan in plans
        )
        return "\n".join(lines)
    except Exception as exc:
        return f"计划列表获取失败：{exc}"
    finally:
        db.close()


@tool
def get_study_plan_detail(plan_id: int, config: RunnableConfig = None) -> str:
    """查看一份学习计划及实时任务进度。"""
    from app.services.study_plan_service import get_study_plan_by_id, get_study_plan_progress

    db = _db()
    try:
        plan = get_study_plan_by_id(db=db, user_id=_user_id(config), plan_id=plan_id)
        if plan is None:
            return "计划不存在或无权限"
        progress = get_study_plan_progress(db=db, plan_id=plan.id)
        return (
            f"《{plan.title}》(ID: {plan.id})\n状态：{plan.status}\n"
            f"起止：{plan.start_date} 至 {plan.end_date}\n"
            f"进度：{progress['completed_tasks']}/{progress['total_tasks']}，"
            f"完成 {progress['progress_percent']}%\n目标：{plan.goal or '未填写'}"
        )
    except Exception as exc:
        return f"计划查询失败：{exc}"
    finally:
        db.close()


@tool
def update_study_plan_status(plan_id: int, status: str, config: RunnableConfig = None) -> str:
    """更新计划状态：draft/active/completed/cancelled。"""
    from app.services.study_plan_service import get_study_plan_by_id, update_study_plan_status as update_status

    db = _db()
    try:
        plan = get_study_plan_by_id(db=db, user_id=_user_id(config), plan_id=plan_id)
        if plan is None:
            return "计划不存在或无权限"
        update_status(db=db, plan=plan, new_status=status)
        return f"计划《{plan.title}》状态已更新为 {status}"
    except Exception as exc:
        return f"状态更新失败：{exc}"
    finally:
        db.close()


@tool
def delete_study_plan(plan_id: int, config: RunnableConfig = None) -> str:
    """删除一份学习计划，保留已创建的独立任务。"""
    from app.services.study_plan_service import delete_study_plan as delete_plan, get_study_plan_by_id

    db = _db()
    try:
        plan = get_study_plan_by_id(db=db, user_id=_user_id(config), plan_id=plan_id)
        if plan is None:
            return "计划不存在或无权限"
        title = plan.title
        delete_plan(db=db, plan=plan, delete_tasks=False)
        return f"学习计划《{title}》已删除"
    except Exception as exc:
        return f"计划删除失败：{exc}"
    finally:
        db.close()


@tool
def create_task(
    title: str,
    course_id: int = 0,
    plan_id: int = 0,
    priority: str = "medium",
    due_date: str = "",
    description: str = "",
    config: RunnableConfig = None,
) -> str:
    """创建任务；传 plan_id 时直接创建该计划下的日程任务。"""
    from app.schemas.study_plan import StudyPlanTaskCreate
    from app.schemas.task import TaskCreate
    from app.services.study_plan_service import create_study_plan_task, get_study_plan_by_id
    from app.services.task_service import create_task as create_task_service

    db = _db()
    try:
        uid = _user_id(config)
        planned = date.fromisoformat(due_date) if due_date else date.today()
        if plan_id > 0:
            plan = get_study_plan_by_id(db=db, user_id=uid, plan_id=plan_id)
            if plan is None:
                return "任务创建失败：计划不存在或无权限"
            result = create_study_plan_task(
                db=db,
                plan=plan,
                user_id=uid,
                task_in=StudyPlanTaskCreate(
                    title=title,
                    description=description or None,
                    planned_date=planned,
                    sequence_no=1,
                    priority=priority,
                    estimated_minutes=None,
                ),
            )
            return f"任务《{result['task'].title}》已加入计划《{plan.title}》（ID: {result['task_id']}）"

        due_at = datetime.combine(planned, time(23, 59, 59)) if due_date else None
        task = create_task_service(
            db=db,
            user_id=uid,
            task_in=TaskCreate(
                title=title,
                course_id=_course_id(course_id, config),
                description=description or None,
                priority=priority,
                due_at=due_at,
                source="agent",
            ),
        )
        return f"任务《{task.title}》创建成功（ID: {task.id}）"
    except Exception as exc:
        return f"任务创建失败：{exc}"
    finally:
        db.close()


@tool
def list_tasks(
    course_id: int = 0,
    status: str = "",
    priority: str = "",
    config: RunnableConfig = None,
) -> str:
    """列出当前用户任务，默认限定当前课程。"""
    from app.services.task_service import list_tasks as list_task_service

    db = _db()
    try:
        total, tasks = list_task_service(
            db=db,
            user_id=_user_id(config),
            course_id=_course_id(course_id, config),
            status=status or None,
            priority=priority or None,
            limit=50,
            offset=0,
        )
        if not tasks:
            return "暂无任务"
        lines = [f"共 {total} 个任务："]
        for task in tasks:
            due = f" · 截止 {task.due_at:%Y-%m-%d}" if task.due_at else ""
            lines.append(f"#{task.id} [{task.status}] [{task.priority}] {task.title}{due}")
        return "\n".join(lines)
    except Exception as exc:
        return f"任务列表获取失败：{exc}"
    finally:
        db.close()


@tool
def update_task_status(task_id: int, status: str, config: RunnableConfig = None) -> str:
    """更新任务状态：pending/in_progress/completed/cancelled。"""
    from app.services.task_service import get_task_by_id, update_task_status as update_status

    db = _db()
    try:
        task = get_task_by_id(db=db, user_id=_user_id(config), task_id=task_id)
        if task is None:
            return "任务不存在或无权限"
        update_status(db=db, task=task, new_status=status)
        return f"任务《{task.title}》状态已更新为 {status}"
    except Exception as exc:
        return f"任务状态更新失败：{exc}"
    finally:
        db.close()


@tool
def delete_task(task_id: int, config: RunnableConfig = None) -> str:
    """删除当前用户的一项任务。"""
    from app.services.task_service import delete_task as delete_task_service, get_task_by_id

    db = _db()
    try:
        task = get_task_by_id(db=db, user_id=_user_id(config), task_id=task_id)
        if task is None:
            return "任务不存在或无权限"
        title = task.title
        delete_task_service(db=db, task=task)
        return f"任务《{title}》已删除"
    except Exception as exc:
        return f"任务删除失败：{exc}"
    finally:
        db.close()


@tool
def get_dashboard_overview(config: RunnableConfig = None) -> str:
    """获取今日任务、学习投入与活跃计划概览。"""
    from app.services.dashboard_service import get_dashboard_overview as dashboard

    db = _db()
    try:
        result = dashboard(
            db=db,
            user_id=_user_id(config),
            trend_days=7,
            task_limit=5,
            plan_limit=5,
        )
        summary = result["summary"]
        return (
            f"学习概览：今日任务 {summary['today_tasks']} 个，"
            f"已完成 {summary['completed_today_tasks']} 个；"
            f"今日学习 {summary['today_study_minutes']} 分钟；"
            f"进行中计划 {summary['active_plans']} 个。"
        )
    except Exception as exc:
        return f"仪表盘获取失败：{exc}"
    finally:
        db.close()
