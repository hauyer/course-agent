from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.search import (
    SemanticSearchRequest,
    SemanticSearchResponse,
    VectorIndexResponse,
)
from app.services.auth_service import get_current_user
from app.services.course_service import get_course_by_id
from app.services.material_service import get_material_by_id
from app.services.vector_service import (
    index_material_vectors,
    semantic_search,
)

router = APIRouter()


@router.post(
    "/materials/{material_id}/vectors/rebuild",
    response_model=VectorIndexResponse
)
def rebuild_material_vectors_api(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    为一份资料重新生成全部向量。
    """

    material = get_material_by_id(
        db=db,
        user_id=current_user.id,
        material_id=material_id
    )

    if material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="资料不存在或无权限访问"
        )

    if material.parse_status != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="资料正文尚未解析成功"
        )

    try:
        indexed_count = index_material_vectors(
            db=db,
            material=material
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"向量生成失败：{exc}"
        ) from exc

    return {
        "material_id": material.id,
        "indexed_count": indexed_count,
        "message": "资料向量生成成功"
    }


@router.post(
    "/search/semantic",
    response_model=SemanticSearchResponse
)
def semantic_search_api(
    search_in: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    在当前用户指定课程内进行语义检索。
    """

    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=search_in.course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    try:
        results = semantic_search(
            db=db,
            user_id=current_user.id,
            course_id=search_in.course_id,
            query=search_in.query,
            top_k=search_in.top_k
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"语义检索失败：{exc}"
        ) from exc

    return {
        "course_id": search_in.course_id,
        "query": search_in.query,
        "total": len(results),
        "results": results
    }