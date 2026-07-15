from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.knowledge_graph import (
    KnowledgeGraphJobResponse,
    KnowledgeGraphResponse,
    KnowledgeGraphVersionsResponse,
)
from app.services.auth_service import get_current_user
from app.services.knowledge_graph_service import (
    KnowledgeGraphConflictError,
    cancel_or_delete_graph_job,
    create_knowledge_graph_job,
    get_active_knowledge_graph,
    get_owned_graph_job,
    list_knowledge_graph_versions,
    process_knowledge_graph_job,
)


router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="课程或知识图谱任务不存在，或无权限访问",
    )


@router.post(
    "/{course_id}/knowledge-graph/jobs",
    response_model=KnowledgeGraphJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="创建课程知识图谱构建任务",
)
def create_knowledge_graph_job_api(
    course_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        job = create_knowledge_graph_job(
            db,
            user_id=current_user.id,
            course_id=course_id,
        )
    except PermissionError as exc:
        raise _not_found() from exc
    except KnowledgeGraphConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if "大模型" in str(exc) or "API" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    background_tasks.add_task(
        process_knowledge_graph_job,
        job_id=job.id,
        user_id=current_user.id,
        course_id=course_id,
    )
    return job


@router.get(
    "/{course_id}/knowledge-graph/jobs/{job_id}",
    response_model=KnowledgeGraphJobResponse,
    summary="查询知识图谱构建进度",
)
def get_knowledge_graph_job_api(
    course_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = get_owned_graph_job(
        db,
        user_id=current_user.id,
        course_id=course_id,
        job_id=job_id,
    )
    if job is None:
        raise _not_found()
    return job


@router.get(
    "/{course_id}/knowledge-graph",
    response_model=KnowledgeGraphResponse,
    summary="查询当前生效的课程知识图谱",
)
def get_active_knowledge_graph_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        graph = get_active_knowledge_graph(
            db,
            user_id=current_user.id,
            course_id=course_id,
        )
    except PermissionError as exc:
        raise _not_found() from exc
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="当前课程还没有成功生成的知识图谱",
        )
    return graph


@router.get(
    "/{course_id}/knowledge-graph/versions",
    response_model=KnowledgeGraphVersionsResponse,
    summary="查询课程知识图谱版本",
)
def list_knowledge_graph_versions_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        items = list_knowledge_graph_versions(
            db,
            user_id=current_user.id,
            course_id=course_id,
        )
    except PermissionError as exc:
        raise _not_found() from exc
    return {"total": len(items), "items": items}


@router.delete(
    "/{course_id}/knowledge-graph/jobs/{job_id}",
    summary="取消或删除知识图谱构建任务",
)
def cancel_or_delete_knowledge_graph_job_api(
    course_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = cancel_or_delete_graph_job(
            db,
            user_id=current_user.id,
            course_id=course_id,
            job_id=job_id,
        )
    except PermissionError as exc:
        raise _not_found() from exc
    except KnowledgeGraphConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": result}
