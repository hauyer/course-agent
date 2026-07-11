from pathlib import Path
from typing import List, Optional
from uuid import uuid4
from starlette.concurrency import run_in_threadpool


from app.utils.file_parser import (
    DocumentParseError,
    parse_document,
)

from fastapi import Query

from app.schemas.material_chunk import (
    MaterialChunkListResponse,
    RebuildChunksResponse,
)
from app.services.material_chunk_service import (
    count_material_chunks,
    get_material_chunks,
    replace_material_chunks,
)
from app.services.vector_service import delete_material_vectors
from app.utils.text_chunker import build_material_chunks

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.material import (
    MaterialResponse,
    MaterialTextResponse,
)
from app.services.auth_service import get_current_user
from app.services.course_service import get_course_by_id
from app.services.material_service import (
    create_material,
    delete_material,
    get_course_materials,
    get_material_by_id,
    mark_material_processing,
    save_material_parse_failure,
    save_material_parse_success,
)

router = APIRouter()

# 允许上传的课程资料类型
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".txt",
    ".md",
}

# 最大文件大小：20 MB
MAX_FILE_SIZE = 20 * 1024 * 1024

# 每次读取 1 MB，避免一次性将大文件全部放入内存
READ_CHUNK_SIZE = 1024 * 1024

# 项目根目录下的 uploads 文件夹
UPLOAD_ROOT = Path("uploads")


@router.post(
    "/courses/{course_id}/materials",
    response_model=MaterialResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_material_api(
    course_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    上传课程资料。

    文件保存在：
    uploads/{user_id}/{course_id}/

    数据库保存：
    原始文件名、唯一文件名、路径、类型、大小和解析状态。
    """

    # 1. 检查课程是否属于当前用户
    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    # 2. 清理原始文件名，防止路径穿越
    original_filename = Path(file.filename or "").name

    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )

    # 3. 检查扩展名
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed_text = "、".join(sorted(ALLOWED_EXTENSIONS))

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持该文件类型，允许的类型为：{allowed_text}"
        )

    # 4. 为文件生成唯一名称
    stored_filename = f"{uuid4().hex}{extension}"

    # 5. 创建用户和课程对应的目录
    save_directory = (
        UPLOAD_ROOT
        / str(current_user.id)
        / str(course_id)
    )

    save_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    save_path = save_directory / stored_filename

    file_size = 0

    try:
        # 6. 分块保存文件，同时检查大小
        with save_path.open("wb") as output_file:
            while True:
                chunk = await file.read(READ_CHUNK_SIZE)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="文件大小不能超过 20 MB"
                    )

                output_file.write(chunk)

        # 7. 不允许上传空文件
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能上传空文件"
            )

        # 8. 标题未填写时，默认使用原文件名去掉扩展名
        material_title = (
            title.strip()
            if title and title.strip()
            else Path(original_filename).stem
        )

        # 使用正斜线保存相对路径，兼容不同操作系统
        relative_file_path = save_path.as_posix()

        # 9. 将元数据写入 MySQL
        material = create_material(
        db=db,
        user_id=current_user.id,
        course_id=course_id,
        title=material_title,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=relative_file_path,
        file_type=extension.lstrip("."),
        mime_type=file.content_type,
        file_size=file_size
    )

        # 10. 开始解析资料正文
        mark_material_processing(
        db=db,
        material=material
         )

        try:
            # 文档解析属于同步阻塞操作，放在线程池中执行，
            # 避免阻塞 FastAPI 事件循环。
            raw_text = await run_in_threadpool(
            parse_document,
            save_path
            )

            material = save_material_parse_success(
            db=db,
            material=material,
            raw_text=raw_text
            )

            chunks = build_material_chunks(
            raw_text,
            chunk_size=800,
            chunk_overlap=120
            )

            if not chunks:
                material = save_material_parse_failure(
                    db=db,
                    material=material,
                    error_message="正文解析成功，但未生成有效资料分块"
                )

                return material

            replace_material_chunks(
                db=db,
                material=material,
                chunks=chunks
            )
        except DocumentParseError as parse_exc:
            # 解析失败不删除原始资料。
            # 文件仍然上传成功，用户可以后续重新解析。
            material = save_material_parse_failure(
                db=db,
                material=material,
                error_message=str(parse_exc)
        )

        except Exception as parse_exc:
            material = save_material_parse_failure(
            db=db,
            material=material,
            error_message=f"资料解析发生未知错误：{parse_exc}"
        )

        return material

    except HTTPException:
        # 上传过程中失败，删除未完成的文件
        if save_path.exists():
            save_path.unlink()

        raise

    except Exception as exc:
        if save_path.exists():
            save_path.unlink()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"资料上传失败：{str(exc)}"
        ) from exc

    finally:
        await file.close()


@router.get(
    "/courses/{course_id}/materials",
    response_model=List[MaterialResponse]
)
def list_course_materials_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取某门课程的资料列表。
    """

    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    return get_course_materials(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )


@router.get(
    "/materials/{material_id}",
    response_model=MaterialResponse
)
def get_material_api(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取资料详情。
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

    return material


@router.delete("/materials/{material_id}")
def delete_material_api(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    同时删除磁盘文件和数据库记录。
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

    file_path = Path(material.file_path)

    try:
        # 先删除向量数据
        delete_material_vectors(material.id)

        # 再删除 MySQL 记录
        delete_material(
            db=db,
            material=material
        )

        # 最后删除磁盘文件
        if file_path.exists():
            file_path.unlink()

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除资料失败：{str(exc)}"
        ) from exc

    return {
        "message": "课程资料删除成功"
    }


@router.get(
    "/materials/{material_id}/text",
    response_model=MaterialTextResponse
)
def get_material_text_api(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    查看资料正文解析结果。

    为避免 Swagger 页面加载过多文本，
    当前只返回前 2000 个字符作为预览。
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

    raw_text = material.raw_text or ""

    return {
        "material_id": material.id,
        "title": material.title,
        "parse_status": material.parse_status,
        "text_length": len(raw_text),
        "text_preview": raw_text[:2000]
    }



@router.post(
    "/materials/{material_id}/parse",
    response_model=MaterialResponse
)
async def parse_material_again_api(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    手动重新解析资料。

    适用于之前解析失败，或者解析规则更新后的场景。
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

    file_path = Path(material.file_path)

    if not file_path.exists():
        material = save_material_parse_failure(
            db=db,
            material=material,
            error_message="原始资料文件不存在"
        )

        return material

    mark_material_processing(
        db=db,
        material=material
    )

    try:
        raw_text = await run_in_threadpool(
            parse_document,
            file_path
        )

        material = save_material_parse_success(
            db=db,
            material=material,
            raw_text=raw_text
        )

        chunks = build_material_chunks(
            raw_text,
            chunk_size=800,
            chunk_overlap=120
        )

        if not chunks:
            material = save_material_parse_failure(
                db=db,
                material=material,
                error_message="正文解析成功，但未生成有效资料分块"
            )

            return material
        # 重新解析后，旧分块对应的向量已经失效
        delete_material_vectors(material.id)

        # 删除旧分块并写入新的分块

        replace_material_chunks(
            db=db,
            material=material,
            chunks=chunks
        )

    except DocumentParseError as exc:
        material = save_material_parse_failure(
            db=db,
            material=material,
            error_message=str(exc)
        )

    except Exception as exc:
        material = save_material_parse_failure(
            db=db,
            material=material,
            error_message=f"资料解析发生未知错误：{exc}"
        )

    return material


@router.get(
    "/materials/{material_id}/chunks",
    response_model=MaterialChunkListResponse
)
def list_material_chunks_api(
    material_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    分页查看一份资料的文本分块。
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

    total = count_material_chunks(
        db=db,
        user_id=current_user.id,
        material_id=material_id
    )

    items = get_material_chunks(
        db=db,
        user_id=current_user.id,
        material_id=material_id,
        skip=skip,
        limit=limit
    )

    return {
        "material_id": material_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items
    }


@router.post(
    "/materials/{material_id}/chunks/rebuild",
    response_model=RebuildChunksResponse
)
def rebuild_material_chunks_api(
    material_id: int,
    chunk_size: int = Query(
        default=800,
        ge=200,
        le=3000
    ),
    chunk_overlap: int = Query(
        default=120,
        ge=0,
        le=500
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    根据不同参数手动重新切分资料正文。
    """

    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chunk_overlap 必须小于 chunk_size"
        )

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

    if not material.raw_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该资料尚未成功解析正文"
        )

    chunks = build_material_chunks(
        material.raw_text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未生成有效资料分块"
        )
    # 清除旧分块对应的 Chroma 向量
    delete_material_vectors(material.id)

    # 用新的分块替换 MySQL 中的旧分块
    chunk_models = replace_material_chunks(
        db=db,
        material=material,
        chunks=chunks
    )

    return {
        "material_id": material.id,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunk_count": len(chunk_models),
        "message": "资料重新分块成功"
    }