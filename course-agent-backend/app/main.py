import time
from uuid import uuid4

from fastapi import FastAPI, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import SessionLocal, get_db
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
    Note,
    NoteSyncRecord,
    LearningRecord,
    CourseProgress,
    IntegrationConfig,
    LlmConfig,
    AgentMemory,
    AuditLog,
    KnowledgeGraphJob,
    KnowledgeNode,
    KnowledgeEdge,
    KnowledgeNodeSource,
    KnowledgeEdgeSource,
)
from app.routers import (
    auth,
    courses,
    materials,
    search,
    agent,
    tasks,
    study_plans,
    notes,
    learning,
    dashboard,
    audit,
    backup,
    knowledge_graph,
)
from app.services.audit_service import write_audit_log
from app.services.knowledge_graph_service import recover_interrupted_knowledge_graph_jobs
from app.services.migration_service import run_database_migrations


# 使用版本化、只增不删的迁移升级空数据库或既有 1.0 数据库。
run_database_migrations()

# 创建FastAPI应用实例，并设置应用的标题、描述和版本信息
app = FastAPI(
    title="课程学习助手Agent平台后端",
    description="负责用户认证、课程管理、资料管理、Agent 问答、学习计划和待办任务等功能",
    version="1.1.0",
)


@app.middleware("http")
async def trace_and_audit_request(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or uuid4().hex
    request.state.trace_id = trace_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    if not request.url.path.startswith("/api/agent/chat"):
        write_audit_log(
            trace_id=trace_id,
            user_id=getattr(request.state, "user_id", None),
            category="http",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=(time.perf_counter() - started) * 1000,
            error_count=1 if response.status_code >= 400 else 0,
            summary=f"{request.method} {request.url.path}",
        )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数不符合要求",
            "errors": exc.errors(),
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", uuid4().hex)
    write_audit_log(
        trace_id=trace_id,
        user_id=getattr(request.state, "user_id", None),
        category="error",
        method=request.method,
        path=request.url.path,
        status_code=500,
        duration_ms=0,
        error_count=1,
        summary="未处理的服务器异常",
        error_detail=f"{type(exc).__name__}: {str(exc)[:1800]}",
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器处理失败", "trace_id": trace_id},
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

# 将笔记路由注册到应用中，所有与笔记相关的API都以 /api/notes/ 开头
app.include_router(
    notes.router,
    prefix="/api/notes",
    tags=["课程笔记"],
)

# 将学习记录路由注册到应用中，所有与学习记录相关的API都以 /api/learning/ 开头
app.include_router(
    learning.router,
    prefix="/api/learning",
    tags=["学习进度"],
)

# 将仪表盘路由注册到应用中，所有与仪表盘相关的API都以 /api/dashboard/ 开头
app.include_router(
    dashboard.router,
    prefix="/api/dashboard",
    tags=["首页统计看板"],
)

app.include_router(
    knowledge_graph.router,
    prefix="/api/courses",
    tags=["课程知识图谱"],
)

app.include_router(
    audit.router,
    prefix="/api/audit",
    tags=["运行审计"],
)

app.include_router(
    backup.router,
    prefix="/api/backup",
    tags=["数据备份"],
)


@app.on_event("startup")
def recover_interrupted_background_jobs():
    db = SessionLocal()
    try:
        recover_interrupted_knowledge_graph_jobs(db)
    finally:
        db.close()

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
        "status": "ok",
        "app": "course-study-desk",
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
