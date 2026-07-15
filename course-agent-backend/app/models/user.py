from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.database import Base

# 定义用户模型类，继承自SQLAlchemy的Base类
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    role = Column(String(20), default="student", nullable=False)
    # 服务端会把头像压缩为 WebP data URL；MySQL 使用 LONGTEXT，测试 SQLite 使用 Text。
    avatar_data = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
