from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.material import Material


def create_material(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    title: str,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    file_type: str,
    mime_type: Optional[str],
    file_size: int
) -> Material:
    """
    创建课程资料记录。
    """

    material = Material(
        user_id=user_id,
        course_id=course_id,
        title=title,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        parse_status="pending"
    )

    try:
        db.add(material)
        db.commit()
        db.refresh(material)
        return material

    except Exception:
        db.rollback()
        raise


def get_course_materials(
    db: Session,
    *,
    user_id: int,
    course_id: int
) -> List[Material]:
    """
    查询当前用户某门课程下的全部资料。
    """

    return (
        db.query(Material)
        .filter(
            Material.user_id == user_id,
            Material.course_id == course_id
        )
        .order_by(Material.created_at.desc())
        .all()
    )


def get_material_by_id(
    db: Session,
    *,
    user_id: int,
    material_id: int
) -> Optional[Material]:
    """
    查询当前用户的一份资料。
    """

    return (
        db.query(Material)
        .filter(
            Material.id == material_id,
            Material.user_id == user_id
        )
        .first()
    )


def delete_material(
    db: Session,
    material: Material
) -> None:
    """
    删除资料数据库记录。
    """

    try:
        db.delete(material)
        db.commit()

    except Exception:
        db.rollback()
        raise

def mark_material_processing(
        db: Session,
        material: Material
) ->Material:
    """
    将资料状态更新为正在解析。
    """ 
    material.parse_status = "processing"
    material.parse_error = None

    try:
        db.commit()
        db.refresh(material)
        return material

    except Exception:
        db.rollback()
        raise


def save_material_parse_success(
    db: Session,
    material: Material,
    raw_text: str
) -> Material:
    """
    保存解析成功后的正文。
    """
    material.raw_text = raw_text
    material.parse_status = "success"
    material.parse_error = None

    try:
        db.commit()
        db.refresh(material)
        return material

    except Exception:
        db.rollback()
        raise


def save_material_parse_failure(
    db: Session,
    material: Material,
    error_message: str
) -> Material:
    """
    保存解析失败状态及错误信息。
    """
    material.raw_text = None
    material.parse_status = "failed"
    material.parse_error = error_message[:1000]

    try:
        db.commit()
        db.refresh(material)
        return material

    except Exception:
        db.rollback()
        raise