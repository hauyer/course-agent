from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base


class MaterialChunk(Base):
    """
    课程资料文本分块。

    每条记录对应资料中的一个可检索文本片段。
    后续向量数据库中的向量，也将与 chunk_id 对应。
    """

    __tablename__ = "material_chunks"

    __table_args__ = (
        UniqueConstraint(
            "material_id",
            "chunk_index",
            name="uq_material_chunk_index"
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    material_id = Column(
        Integer,
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 当前资料中的分块序号，从 0 开始
    chunk_index = Column(
        Integer,
        nullable=False
    )

    # PDF、PPT 可以记录页码；TXT、DOCX 可为空
    page_no = Column(
        Integer,
        nullable=True,
        index=True
    )

    # 分块正文
    content = Column(
        LONGTEXT,
        nullable=False
    )

    # 字符数量，便于统计
    char_count = Column(
        Integer,
        nullable=False
    )

    # 下一步接入向量数据库后保存向量记录 ID
    vector_id = Column(
        String(255),
        nullable=True,
        unique=True
    )

    # pending、success、failed
    vector_status = Column(
        String(30),
        nullable=False,
        default="pending",
        index=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )