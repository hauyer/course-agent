from sqlalchemy import(
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base



class Material(Base):
    """
    课程资料表。

    文件本体保存在 uploads 目录中；
    数据库只保存文件路径、文件信息和后续解析出来的文本。
    """
    
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 资料所属课程
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

     # 用户设置的资料标题
    title = Column(
        String(255),
        nullable=False
    )

    # 用户上传时的原始文件名
    original_filename = Column(
        String(255),
        nullable=False
    )

    # 后端生成的唯一文件名
    stored_filename = Column(
        String(255),
        nullable=False,
        unique=True
    )

    # 相对存储路径
    file_path = Column(
        String(500),
        nullable=False
    )

    # 文件扩展名，如 pdf、docx
    file_type = Column(
        String(30),
        nullable=False,
        index=True
    )

    # MIME 类型
    mime_type = Column(
        String(100),
        nullable=True
    )

    # 文件大小，单位为字节
    file_size = Column(
        BigInteger,
        nullable=False,
        default=0
    )

    # pending、success、failed
    parse_status = Column(
        String(30),
        nullable=False,
        default="pending",
        index=True
    )

    # 后续解析 PDF、Word 后保存正文
    raw_text = Column(
        LONGTEXT,
        nullable=True
    )

    # 解析失败时记录原因
    parse_error = Column(
        String(1000),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )