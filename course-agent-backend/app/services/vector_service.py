from __future__ import annotations

import math
import threading
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.material import Material
from app.models.material_chunk import MaterialChunk


COSINE_SPACE = "cosine"
DEFAULT_COSINE_COLLECTION = "course_material_chunks_v1_1_cosine"
LEGACY_COLLECTION_NAME = "course_material_chunks"


class VectorServiceError(RuntimeError):
    """Base error for a vector runtime failure safe to map to a business error."""


class CollectionMetricError(VectorServiceError):
    """The selected collection does not use the required cosine space."""


class EmbeddingValidationError(VectorServiceError):
    """The embedding runtime returned invalid or incompatible vectors."""


_runtime_lock = threading.RLock()
_encode_lock = threading.RLock()
_embedding_model: SentenceTransformer | None = None
_embedding_model_name: str | None = None
_chroma_client: Any | None = None
_chroma_client_path: str | None = None
_chroma_collections: dict[str, Any] = {}


def get_embedding_model() -> SentenceTransformer:
    """Lazily load and reuse the configured SentenceTransformer safely."""

    global _embedding_model, _embedding_model_name
    settings = get_settings()
    with _runtime_lock:
        if _embedding_model is None or _embedding_model_name != settings.embedding_model_name:
            try:
                _embedding_model = SentenceTransformer(settings.embedding_model_name)
            except Exception as exc:  # pragma: no cover - exact library errors vary
                raise VectorServiceError("向量模型加载失败") from exc
            _embedding_model_name = settings.embedding_model_name
        return _embedding_model


def _collection_space(collection: Any) -> str | None:
    configuration = getattr(collection, "configuration", None) or {}
    if isinstance(configuration, dict):
        hnsw = configuration.get("hnsw") or {}
        if isinstance(hnsw, dict) and hnsw.get("space"):
            return str(hnsw["space"]).lower()

    # Read-only compatibility for collections created with Chroma's legacy
    # metadata configuration. New 1.1 collections never use this form.
    metadata = getattr(collection, "metadata", None) or {}
    if isinstance(metadata, dict) and metadata.get("hnsw:space"):
        return str(metadata["hnsw:space"]).lower()
    return None


def validate_collection_metric(collection: Any) -> None:
    """Reject an existing collection unless it is explicitly cosine."""

    space = _collection_space(collection)
    if space != COSINE_SPACE:
        name = getattr(collection, "name", "<unknown>")
        raise CollectionMetricError(
            f"Chroma collection '{name}' 的距离空间为 {space or 'unknown'}，"
            "1.1 检索要求显式 cosine；请使用新的 collection 名称重建向量"
        )


def get_chroma_client() -> Any:
    global _chroma_client, _chroma_client_path, _chroma_collections
    settings = get_settings()
    with _runtime_lock:
        if _chroma_client is None or _chroma_client_path != settings.chroma_path:
            try:
                _chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
            except Exception as exc:  # pragma: no cover - external runtime
                raise VectorServiceError("ChromaDB 初始化失败") from exc
            _chroma_client_path = settings.chroma_path
            _chroma_collections = {}
        return _chroma_client


def get_chroma_collection(*, collection_name: str | None = None) -> Any:
    """Get/create a collection with Chroma 1.5's explicit cosine config."""

    settings = get_settings()
    name = (collection_name or settings.chroma_collection_name).strip()
    if not name:
        raise ValueError("Chroma collection 名称不能为空")

    with _runtime_lock:
        cached = _chroma_collections.get(name)
        if cached is not None:
            validate_collection_metric(cached)
            return cached

        client = get_chroma_client()
        try:
            collection = client.get_or_create_collection(
                name=name,
                configuration={"hnsw": {"space": COSINE_SPACE}},
            )
        except Exception as exc:
            raise VectorServiceError("ChromaDB collection 获取失败") from exc
        validate_collection_metric(collection)
        _chroma_collections[name] = collection
        return collection


def validate_unit_vectors(vectors: list[list[float]], *, tolerance: float = 1e-4) -> None:
    for vector in vectors:
        norm = math.sqrt(sum(value * value for value in vector))
        if abs(norm - 1.0) >= tolerance:
            raise EmbeddingValidationError(f"归一化向量模长异常：{norm:.6f}")


def encode_texts(
    texts: list[str],
    *,
    normalize: bool = True,
    validate_norms: bool | None = None,
) -> list[list[float]]:
    """Encode non-empty text with one model and a validated vector contract."""

    if not texts:
        return []
    if not normalize:
        raise ValueError("1.1 cosine collection 只接受归一化向量")
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("空字符串或纯空白文本不能生成向量")

    settings = get_settings()
    model = get_embedding_model()
    try:
        with _encode_lock:
            encoded = model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
    except Exception as exc:  # pragma: no cover - exact library errors vary
        raise VectorServiceError("文本向量生成失败") from exc

    try:
        rows = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        vectors = [[float(value) for value in row] for row in rows]
    except (TypeError, ValueError) as exc:
        raise EmbeddingValidationError("向量模型返回了无法解析的数据") from exc

    if len(vectors) != len(texts):
        raise EmbeddingValidationError("向量数量与输入文本数量不一致")
    dimensions = {len(vector) for vector in vectors}
    if not dimensions or dimensions == {0} or len(dimensions) != 1:
        raise EmbeddingValidationError("向量维度为空或不一致")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise EmbeddingValidationError("向量包含 NaN 或 Infinity")

    should_validate_norms = (
        settings.embedding_validate_norms if validate_norms is None else validate_norms
    )
    if should_validate_norms:
        validate_unit_vectors(vectors)
    return vectors


def embedding_version() -> str:
    model_name = get_settings().embedding_model_name.rsplit("/", 1)[-1]
    return f"{model_name}_normalized_v1"


def delete_material_vectors(
    *,
    user_id: int,
    course_id: int,
    material_id: int,
    collection: Any | None = None,
) -> None:
    """Delete only the current 1.1 collection's strictly scoped vectors."""

    if min(user_id, course_id, material_id) < 1:
        raise ValueError("删除向量需要有效的用户、课程和资料 ID")
    target = collection or get_chroma_collection()
    target.delete(
        where={
            "$and": [
                {"user_id": int(user_id)},
                {"course_id": int(course_id)},
                {"material_id": int(material_id)},
            ]
        }
    )


def _metadata_for_chunk(chunk: MaterialChunk, material: Material) -> dict[str, Any]:
    return {
        "user_id": int(chunk.user_id),
        "course_id": int(chunk.course_id),
        "material_id": int(chunk.material_id),
        "chunk_id": int(chunk.id),
        "chunk_index": int(chunk.chunk_index),
        "page_no": int(chunk.page_no) if chunk.page_no is not None else -1,
        "file_type": material.file_type or "unknown",
        "embedding_version": embedding_version(),
    }


def index_material_vectors(
    db: Session,
    *,
    material: Material,
    collection: Any | None = None,
) -> int:
    """Rebuild one owned material in the active 1.1 cosine collection."""

    if not material.id or not material.user_id or not material.course_id:
        raise ValueError("资料缺少有效的用户或课程归属")
    chunks = (
        db.query(MaterialChunk)
        .filter(
            MaterialChunk.material_id == material.id,
            MaterialChunk.user_id == material.user_id,
            MaterialChunk.course_id == material.course_id,
        )
        .order_by(MaterialChunk.chunk_index.asc())
        .all()
    )
    chunks = [chunk for chunk in chunks if (chunk.content or "").strip()]
    if not chunks:
        raise ValueError("该资料没有可向量化的文本分块")

    target = collection or get_chroma_collection()
    delete_material_vectors(
        user_id=material.user_id,
        course_id=material.course_id,
        material_id=material.id,
        collection=target,
    )
    try:
        texts = [chunk.content for chunk in chunks]
        embeddings = encode_texts(texts)
        vector_ids = [f"chunk_{chunk.id}" for chunk in chunks]
        target.upsert(
            ids=vector_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=[_metadata_for_chunk(chunk, material) for chunk in chunks],
        )
        for chunk, vector_id in zip(chunks, vector_ids):
            chunk.vector_id = vector_id
            chunk.vector_status = "success"
        db.commit()
        return len(chunks)
    except Exception:
        db.rollback()
        try:
            delete_material_vectors(
                user_id=material.user_id,
                course_id=material.course_id,
                material_id=material.id,
                collection=target,
            )
        except Exception:
            pass
        (
            db.query(MaterialChunk)
            .filter(
                MaterialChunk.material_id == material.id,
                MaterialChunk.user_id == material.user_id,
                MaterialChunk.course_id == material.course_id,
            )
            .update(
                {MaterialChunk.vector_id: None, MaterialChunk.vector_status: "failed"},
                synchronize_session=False,
            )
        )
        db.commit()
        raise


def index_material_vectors_background(*, material_id: int, user_id: int) -> None:
    """Build vectors after upload using a database session owned by the task."""

    db = SessionLocal()
    try:
        material = (
            db.query(Material)
            .filter(Material.id == material_id, Material.user_id == user_id)
            .first()
        )
        if material is None:
            return
        (
            db.query(MaterialChunk)
            .filter(
                MaterialChunk.material_id == material_id,
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == material.course_id,
            )
            .update({MaterialChunk.vector_status: "processing"}, synchronize_session=False)
        )
        db.commit()
        index_material_vectors(db, material=material)
    except Exception:
        db.rollback()
        material = (
            db.query(Material)
            .filter(Material.id == material_id, Material.user_id == user_id)
            .first()
        )
        if material is not None:
            (
                db.query(MaterialChunk)
                .filter(
                    MaterialChunk.material_id == material_id,
                    MaterialChunk.user_id == user_id,
                    MaterialChunk.course_id == material.course_id,
                )
                .update(
                    {MaterialChunk.vector_id: None, MaterialChunk.vector_status: "failed"},
                    synchronize_session=False,
                )
            )
            db.commit()
    finally:
        db.close()


def semantic_search(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    query: str,
    top_k: int = 5,
    min_similarity: float | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible wrapper around the one canonical retrieval service."""

    from app.services.course_retrieval_service import retrieve_course_chunks

    return [
        item.to_dict()
        for item in retrieve_course_chunks(
            db,
            user_id=user_id,
            course_id=course_id,
            query=query,
            top_k=top_k,
            min_similarity=min_similarity,
        )
    ]


def reset_vector_runtime_for_tests() -> None:
    """Clear process caches. Tests only; never deletes persistent data."""

    global _embedding_model, _embedding_model_name
    global _chroma_client, _chroma_client_path, _chroma_collections
    with _runtime_lock:
        _embedding_model = None
        _embedding_model_name = None
        _chroma_client = None
        _chroma_client_path = None
        _chroma_collections = {}
