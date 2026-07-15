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


def _get_db():
    from app.database import SessionLocal
    return SessionLocal()


def _find_course_by_name(db, user_id: int, name: str):
    from app.services.course_service import get_user_courses
    courses = get_user_courses(db, user_id=user_id)
    name_lower = name.lower()
    for c in courses:
        if name_lower in (c.name or "").lower():
            return c
    return None


@tool
def search_materials(course_name: str, config: RunnableConfig) -> str:
    """根据课程名搜索该课程下的所有学习资料。course_name 如 python、数学、机器学习。"""
    from app.services.material_service import get_course_materials
    db = _get_db()
    try:
        course = _find_course_by_name(db, _get_user_id(config), course_name)
        if not course:
            return f"未找到课程'{course_name}'，请先创建课程"

        materials = get_course_materials(db, user_id=_get_user_id(config), course_id=course.id)
        if not materials:
            return f"'{course.name}'暂无学习资料"

        lines = []
        for m in materials:
            preview = ""
            if m.raw_text:
                preview = m.raw_text[:200].replace("\n", " ")
            lines.append(f"{m.title}：{preview}" if preview else m.title)
        return "\n".join(lines)
    except Exception as e:
        return f"资料查询失败：{e}"
    finally:
        db.close()


@tool
def add_material(course_name: str, title: str, content: str, config: RunnableConfig) -> str:
    """为指定课程添加学习资料。course_name 课程名，title 资料标题，content 资料内容。"""
    from app.services.material_service import create_material
    db = _get_db()
    try:
        user_id = _get_user_id(config)
        course = _find_course_by_name(db, user_id, course_name)
        if not course:
            return f"未找到课程'{course_name}'，请先创建课程"

        material = create_material(
            db,
            user_id=user_id,
            course_id=course.id,
            title=title,
            original_filename=f"{title}.txt",
            stored_filename=f"tool_{title}.txt",
            file_path=f"tool/{user_id}/{course.id}/{title}.txt",
            file_type="txt",
            mime_type="text/plain",
            file_size=len(content.encode("utf-8")),
        )

        material.raw_text = content
        material.parse_status = "success"
        db.commit()

        # 文本分块 + 向量化，使资料立即可语义检索
        from app.utils.text_chunker import build_material_chunks
        from app.services.material_chunk_service import replace_material_chunks
        from app.services.vector_service import index_material_vectors

        chunks = build_material_chunks(content, chunk_size=800, chunk_overlap=120)
        if chunks:
            replace_material_chunks(db, material=material, chunks=chunks)
            index_material_vectors(db, material=material)

        return f"已为'{course.name}'添加资料《{title}》（ID: {material.id}）"
    except Exception as e:
        db.rollback()
        return f"资料添加失败：{e}"
    finally:
        db.close()


@tool
def list_materials(config: RunnableConfig) -> str:
    """列出所有课程的学习资料汇总。"""
    from app.services.course_service import get_user_courses
    from app.services.material_service import get_course_materials
    db = _get_db()
    try:
        user_id = _get_user_id(config)
        courses = get_user_courses(db, user_id=user_id)
        if not courses:
            return "暂无课程"

        lines = []
        for c in courses:
            materials = get_course_materials(db, user_id=user_id, course_id=c.id)
            lines.append(f"【{c.name}】共{len(materials)}份资料")
            for m in materials:
                lines.append(f"  - {m.title}")
        return "\n".join(lines) if lines else "暂无任何学习资料"
    except Exception as e:
        return f"资料列表获取失败：{e}"
    finally:
        db.close()


@tool
def delete_material(material_id: int, config: RunnableConfig = None) -> str:
    """删除学习资料及其文件。material_id 资料ID。"""
    from app.services.material_service import get_material_by_id, delete_material as svc_delete
    from app.services.vector_service import delete_material_vectors

    db = _get_db()
    try:
        material = get_material_by_id(
            db=db, user_id=_get_user_id(config), material_id=material_id
        )
        if material is None:
            return "资料不存在或无权限"
        delete_material_vectors(material.id)
        svc_delete(db=db, material=material)
        return f"资料《{material.title}》已删除"
    except Exception as e:
        return f"资料删除失败：{e}"
    finally:
        db.close()
