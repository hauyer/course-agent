from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import Base, engine, get_db
from app.models import (
    User,
    Course,
    Material,
    MaterialChunk,
    ChatSession,
    ChatMessage,
    Task,
    StudyPlan,
    StudyPlanTask,
)
from app.routers import (
    auth,
    courses,
    materials,
    search,
    agent,
    tasks,
    study_plans,
)


#启动时自动创建数据库表
Base.metadata.create_all(bind=engine)

# 创建FastAPI应用实例，并设置应用的标题、描述和版本信息
app = FastAPI(
    title="课程学习助手Agent平台后端",
    description="负责用户认证、课程管理、资料管理、Agent 问答、学习计划和待办任务等功能",
    version="1.0.0",
)


# 将认证路由注册到应用中，所有与用户认证相关的API都以 /api/auth/ 开头
app.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["用户认证"]
)

# 将课程路由注册到应用中，所有与课程管理相关的API都以 /api/courses/ 开头
app.include_router(
    courses.router,
    prefix="/api/courses",
    tags=["课程管理"]
)

# 将资料路由注册到应用中，所有与资料管理相关的API都以 /api/materials/ 开头
app.include_router(
    materials.router,
    prefix="/api",
    tags=["课程资料管理"]
)

# 将向量检索路由注册到应用中，所有与向量检索相关的API都以 /api/ 开头
app.include_router(
    search.router,
    prefix="/api",
    tags=["向量检索"]
)

# 将Agent路由注册到应用中，所有与Agent问答相关的API都以 /api/agent/ 开头
app.include_router(
    agent.router,
    prefix="/api",
    tags=["Agent问答"],
)

# 将任务路由注册到应用中，所有与学习计划和待办任务相关的API都以 /api/tasks/ 开头
app.include_router(
    tasks.router,
    prefix="/api/tasks",
    tags=["待办任务"],
)

# 将学习计划路由注册到应用中，所有与学习计划相关的API都以 /api/study-plans/ 开头
app.include_router(
    study_plans.router,
    prefix="/api/study-plans",
    tags=["学习计划"],
)

# 定义根路径的GET请求处理函数，返回一个欢迎信息和应用状态
@app.get("/")
def root():
    return {
        "message": "课程学习助手后端启动成功",
        "status": "running"
    }


# 定义健康检查的GET请求处理函数，返回应用的运行状态
@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


# 定义数据库检查的GET请求处理函数，使用依赖注入获取数据库会话，并执行SQL查询以获取当前数据库名称
@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    database_name = db.execute(text("SELECT DATABASE()")).scalar()
    return{
    "message":"MySQL database is accessible",
    "database_name": database_name
    }


@app.get("/tables-check")
def tables_check(db: Session = Depends(get_db)):
    result = db.execute(text("SHOW TABLES")).fetchall()
    tables = [row[0] for row in result]

    return {
        "message": "数据表检查成功",
        "tables": tables
    }