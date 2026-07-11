from sqlalchemy.orm import Session

from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.utils.text_chunker import TextChunk


def replace_material_chunks(
    db: Session,
    *,
    material: Material,
    chunks: list[TextChunk]
) -> list[MaterialChunk]:
    """
    删除资料原有分块，然后写入新的分块。

    这样重新解析或重新分块时，不会残留旧数据。
    """

    try:
        db.query(MaterialChunk).filter(
            MaterialChunk.material_id == material.id
        ).delete(synchronize_session=False)

        chunk_models = [
            MaterialChunk(
                user_id=material.user_id,
                course_id=material.course_id,
                material_id=material.id,
                chunk_index=chunk.chunk_index,
                page_no=chunk.page_no,
                content=chunk.content,
                char_count=chunk.char_count,
                vector_status="pending"
            )
            for chunk in chunks
        ]

        db.add_all(chunk_models)
        db.commit()

        for chunk_model in chunk_models:
            db.refresh(chunk_model)

        return chunk_models

    except Exception:
        db.rollback()
        raise


def get_material_chunks(
    db: Session,
    *,
    user_id: int,
    material_id: int,
    skip: int = 0,
    limit: int = 20
) -> list[MaterialChunk]:
    """
    分页查询当前用户某份资料的分块。
    """

    return (
        db.query(MaterialChunk)
        .filter(
            MaterialChunk.user_id == user_id,
            MaterialChunk.material_id == material_id
        )
        .order_by(MaterialChunk.chunk_index.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_material_chunks(
    db: Session,
    *,
    user_id: int,
    material_id: int
) -> int:
    """
    查询资料分块总数。
    """

    return (
        db.query(MaterialChunk)
        .filter(
            MaterialChunk.user_id == user_id,
            MaterialChunk.material_id == material_id
        )
        .count()
    )