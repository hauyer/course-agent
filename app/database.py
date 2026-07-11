# 导入必要的Python模块
import os  # 用于操作操作系统相关的功能，如环境变量

# 从dotenv库中导入load_dotenv函数，用于从.env文件加载环境变量
from dotenv import load_dotenv
# 从SQLAlchemy库中导入创建引擎的函数
from sqlalchemy import create_engine
# 从SQLAlchemy ORM中导入会话工厂和基类
from sqlalchemy.orm import sessionmaker,declarative_base

# 加载.env文件中的环境变量
load_dotenv()

# 从环境变量中获取数据库URL
DATABASE_URL = os.getenv("DATABASE_URL")

# 检查是否成功获取到数据库URL，如果没有则抛出运行时错误
if not DATABASE_URL:
    raise RuntimeError("没有检测到DATABASE_URL环境变量，请检查.env文件")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    """创建一个数据库会话，并在使用后关闭它"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()