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


def _course_id(course_id: int, config: RunnableConfig | None) -> int:
    return course_id if course_id > 0 else _config_int(config, "course_id", 0)


def _db():
    from app.database import SessionLocal
    return SessionLocal()


@tool
def create_note(
    title: str,
    content: str,
    course_id: int = 0,
    config: RunnableConfig = None,
) -> str:
    """创建课程笔记。content 使用 Markdown；未传 course_id 时使用当前会话课程。"""
    from app.schemas.note import NoteCreate
    from app.services.course_service import get_course_by_id
    from app.services.note_service import create_note as create_note_service

    db = _db()
    try:
        uid, cid = _user_id(config), _course_id(course_id, config)
        if cid <= 0 or get_course_by_id(db=db, user_id=uid, course_id=cid) is None:
            return "笔记创建失败：请选择一门有权限访问的课程"
        note = create_note_service(
            db=db,
            user_id=uid,
            note_in=NoteCreate(
                course_id=cid,
                title=title,
                content_markdown=content,
                tags=[],
                note_type="manual",
                source="agent",
            ),
        )
        return f"笔记《{note.title}》创建成功（ID: {note.id}，课程 #{cid}）"
    except Exception as exc:
        return f"笔记创建失败：{exc}"
    finally:
        db.close()


@tool
def search_notes(
    keyword: str = "",
    course_id: int = 0,
    limit: int = 20,
    config: RunnableConfig = None,
) -> str:
    """搜索当前用户笔记；默认限定当前会话课程。"""
    from app.services.note_service import list_notes

    db = _db()
    try:
        cid = _course_id(course_id, config)
        total, notes = list_notes(
            db=db,
            user_id=_user_id(config),
            course_id=cid if cid > 0 else None,
            keyword=keyword or None,
            limit=max(1, min(limit, 50)),
            offset=0,
        )
        if not notes:
            return "暂无匹配的笔记"
        lines = [f"找到 {total} 条笔记，当前展示 {len(notes)} 条："]
        for note in notes:
            preview = (note.content_markdown or "")[:100].replace("\n", " ")
            lines.append(f"#{note.id} 《{note.title}》[课程 #{note.course_id}] — {preview}")
        return "\n".join(lines)
    except Exception as exc:
        return f"笔记搜索失败：{exc}"
    finally:
        db.close()


@tool
def get_note_detail(note_id: int, config: RunnableConfig = None) -> str:
    """查看一篇有权访问的笔记全文。"""
    from app.services.note_service import get_note_by_id

    db = _db()
    try:
        note = get_note_by_id(db=db, user_id=_user_id(config), note_id=note_id)
        if note is None:
            return "笔记不存在或无权限"
        return (
            f"《{note.title}》(ID: {note.id})\n课程：#{note.course_id}\n"
            f"更新于：{note.updated_at.strftime('%Y-%m-%d %H:%M')}\n---\n"
            f"{note.content_markdown or '(空内容)'}"
        )
    except Exception as exc:
        return f"笔记查询失败：{exc}"
    finally:
        db.close()


@tool
def update_note(
    note_id: int,
    title: str = "",
    content: str = "",
    config: RunnableConfig = None,
) -> str:
    """更新笔记标题或 Markdown 内容。"""
    from app.schemas.note import NoteUpdate
    from app.services.note_service import get_note_by_id, update_note as update_note_service

    db = _db()
    try:
        note = get_note_by_id(db=db, user_id=_user_id(config), note_id=note_id)
        if note is None:
            return "笔记不存在或无权限"
        values = {}
        if title:
            values["title"] = title
        if content:
            values["content_markdown"] = content
        if not values:
            return "未提供要修改的内容"
        update_note_service(db=db, note=note, note_in=NoteUpdate(**values))
        return f"笔记《{note.title}》已更新"
    except Exception as exc:
        return f"笔记更新失败：{exc}"
    finally:
        db.close()


@tool
def delete_note(note_id: int, config: RunnableConfig = None) -> str:
    """删除当前用户的一篇笔记。"""
    from app.services.note_service import delete_note as delete_note_service, get_note_by_id

    db = _db()
    try:
        note = get_note_by_id(db=db, user_id=_user_id(config), note_id=note_id)
        if note is None:
            return "笔记不存在或无权限"
        title = note.title
        delete_note_service(db=db, note=note)
        return f"笔记《{title}》已删除"
    except Exception as exc:
        return f"笔记删除失败：{exc}"
    finally:
        db.close()


def _sync_note(note_id: int, provider: str, config: RunnableConfig | None) -> str:
    from app.services.course_service import get_course_by_id
    from app.services.integration_config_service import (
        get_integration_config,
        require_notion_runtime,
        require_obsidian_runtime,
    )
    from app.services.note_service import get_note_by_id

    db = _db()
    try:
        uid = _user_id(config)
        note = get_note_by_id(db=db, user_id=uid, note_id=note_id)
        if note is None:
            return "笔记不存在或无权限"
        course = get_course_by_id(db=db, user_id=uid, course_id=note.course_id)
        integration = get_integration_config(db, user_id=uid)
        if provider == "notion":
            from app.services.notion_service import notion_config_context, sync_note_to_notion
            with notion_config_context(require_notion_runtime(integration)):
                record = sync_note_to_notion(db=db, note=note, course=course)
            return f"笔记已同步到 Notion：{record.external_path or record.external_id}"
        from app.services.obsidian_service import obsidian_config_context, sync_note_to_obsidian
        with obsidian_config_context(require_obsidian_runtime(integration)):
            record = sync_note_to_obsidian(db=db, note=note, course=course)
        return f"笔记已同步到 Obsidian：{record.external_path}"
    except Exception as exc:
        return f"{provider.title()} 同步失败：{exc}"
    finally:
        db.close()


@tool
def sync_note_to_obsidian(note_id: int, config: RunnableConfig = None) -> str:
    """使用当前用户配置将笔记同步到 Obsidian。"""
    return _sync_note(note_id, "obsidian", config)


@tool
def sync_note_to_notion(note_id: int, config: RunnableConfig = None) -> str:
    """使用当前用户配置将笔记同步到 Notion。"""
    return _sync_note(note_id, "notion", config)


@tool
def list_note_sync_records(note_id: int, config: RunnableConfig = None) -> str:
    """查看当前用户笔记的外部同步记录。"""
    from app.services.note_service import get_note_by_id, list_note_sync_records as list_records

    db = _db()
    try:
        note = get_note_by_id(db=db, user_id=_user_id(config), note_id=note_id)
        if note is None:
            return "笔记不存在或无权限"
        records = list_records(db=db, note_id=note.id)
        if not records:
            return "暂无同步记录"
        lines = [f"笔记 #{note_id} 同步记录："]
        for record in records:
            when = record.last_synced_at.strftime("%m-%d %H:%M") if record.last_synced_at else "尚未成功"
            lines.append(f"[{record.sync_status}] {record.provider} · {when}")
        return "\n".join(lines)
    except Exception as exc:
        return f"同步记录查询失败：{exc}"
    finally:
        db.close()
