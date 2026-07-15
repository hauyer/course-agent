from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from dotenv import load_dotenv

load_dotenv()


def _get_user_id(config: RunnableConfig) -> int:
    try:
        user_id = int((config or {}).get("configurable", {}).get("user_id"))
    except (ValueError, TypeError):
        raise ValueError("无法确定当前用户")
    if user_id < 1:
        raise ValueError("无法确定当前用户")
    return user_id


def _get_course_id(course_id: int, config: RunnableConfig) -> int:
    if course_id > 0:
        return course_id
    try:
        return int((config or {}).get("configurable", {}).get("course_id", 0))
    except (ValueError, TypeError):
        return 0


def _get_db():
    from app.database import SessionLocal

    return SessionLocal()


@tool
def create_learning_record(
    content_summary: str,
    course_id: int = 0,
    duration_minutes: int = 60,
    config: RunnableConfig = None,
) -> str:
    """创建学习记录，记录每天的学习内容和时长。course_id 课程ID，content_summary 学习内容摘要，duration_minutes 学习时长(分钟)。"""
    from app.services.learning_service import (
        create_learning_record as svc_create,
        get_learning_record_by_id,
    )
    from app.schemas.learning import LearningRecordCreate

    db = _get_db()
    try:
        effective_course_id = _get_course_id(course_id, config)
        if effective_course_id <= 0:
            return "学习记录创建失败：请先选择课程"
        record_in = LearningRecordCreate(
            course_id=effective_course_id,
            content_summary=content_summary,
            duration_minutes=duration_minutes,
            source="manual",
        )
        record = svc_create(
            db=db, user_id=_get_user_id(config), record_in=record_in
        )
        return f"已记录学习内容：课程 #{effective_course_id}，时长 {record.duration_minutes} 分钟（ID: {record.id}）"
    except Exception as e:
        return f"学习记录创建失败：{e}"
    finally:
        db.close()


@tool
def list_learning_records(
    course_id: int = 0, limit: int = 20, config: RunnableConfig = None
) -> str:
    """列出学习记录。course_id 课程ID（0表示所有课程），limit 返回条数。"""
    from app.services.learning_service import list_learning_records as svc_list

    db = _get_db()
    try:
        selected = _get_course_id(course_id, config)
        cid = selected if selected > 0 else None
        total, records = svc_list(
            db=db, user_id=_get_user_id(config), course_id=cid, limit=limit
        )
        if not records:
            return "暂无学习记录"
        lines = [f"共 {total} 条记录："]
        for r in records:
            course_info = f"[课程#{r.course_id}]" if r.course_id else ""
            lines.append(
                f"  {r.studied_at.strftime('%m-%d %H:%M')} {course_info} "
                f"{r.duration_minutes}分钟 — {r.content_summary or '无摘要'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"学习记录查询失败：{e}"
    finally:
        db.close()


@tool
def get_learning_summary(
    course_id: int = 0, config: RunnableConfig = None
) -> str:
    """获取学习总结摘要，包含总学习时长、今日时长、任务统计等。course_id 0表示全部课程。"""
    from app.services.learning_service import get_learning_summary as svc_summary

    db = _get_db()
    try:
        selected = _get_course_id(course_id, config)
        cid = selected if selected > 0 else None
        summary = svc_summary(db=db, user_id=_get_user_id(config), course_id=cid)
        return (
            f"学习总结：\n"
            f"  总学习时长：{summary['total_study_minutes']} 分钟\n"
            f"  今日学习：{summary['today_study_minutes']} 分钟\n"
            f"  近7天：{summary['recent_7_days_minutes']} 分钟\n"
            f"  学习记录数：{summary['learning_record_count']}\n"
            f"  任务：{summary['completed_tasks']}/{summary['total_tasks']} 已完成"
            f"（{summary['overdue_tasks']} 个逾期）\n"
            f"  课程：{summary['active_courses']} 进行中，{summary['completed_courses']} 已完成"
        )
    except Exception as e:
        return f"学习总结获取失败：{e}"
    finally:
        db.close()


@tool
def get_course_progress(course_id: int, config: RunnableConfig = None) -> str:
    """查看某门课程的学习进度。course_id 课程ID。"""
    from app.services.learning_service import get_course_progress_detail

    db = _get_db()
    try:
        progress = get_course_progress_detail(
            db=db, user_id=_get_user_id(config), course_id=course_id
        )
        return (
            f"课程 #{course_id} 进度：\n"
            f"  完成度：{progress['progress_percent']}%\n"
            f"  状态：{progress['status']}\n"
            f"  累计学习：{progress['total_study_minutes']} 分钟\n"
            f"  学习记录：{progress['learning_record_count']} 条\n"
            f"  任务进度：{progress['completed_tasks']}/{progress['total_tasks']}"
        )
    except Exception as e:
        return f"课程进度查询失败：{e}"
    finally:
        db.close()


@tool
def delete_learning_record(record_id: int, config: RunnableConfig = None) -> str:
    """删除一条学习记录。record_id 记录ID。"""
    from app.services.learning_service import (
        get_learning_record_by_id,
        delete_learning_record as svc_delete,
    )

    db = _get_db()
    try:
        record = get_learning_record_by_id(
            db=db, user_id=_get_user_id(config), record_id=record_id
        )
        if record is None:
            return "该学习记录不存在或无权限"
        svc_delete(db=db, record=record)
        return "学习记录已删除"
    except Exception as e:
        return f"学习记录删除失败：{e}"
    finally:
        db.close()
