import os
from typing import Any, Optional

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.models.material import Material
from app.models.material_chunk import MaterialChunk

load_dotenv()

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

CHROMA_PATH = os.getenv(
    "CHROMA_PATH",
    "./chroma_db"
)

CHROMA_COLLECTION = os.getenv(
    "CHROMA_COLLECTION",
    "course_material_chunks"
)

_embedding_model: Optional[SentenceTransformer] = None
_chroma_client = None
_chroma_collection = None


def get_embedding_model() -> SentenceTransformer:
    """
    延迟加载向量模型。

    只有第一次真正生成向量时才加载模型，
    避免 FastAPI 启动时立即占用较多时间和内存。
    """
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(
            EMBEDDING_MODEL_NAME
        )

    return _embedding_model


def get_chroma_collection():
    """
    获取本地持久化 Chroma 集合。
    """
    global _chroma_client
    global _chroma_collection

    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PATH
        )

    if _chroma_collection is None:
        _chroma_collection = (
            _chroma_client.get_or_create_collection(
                name=CHROMA_COLLECTION
            )
        )

    return _chroma_collection


def encode_texts(texts: list[str]) -> list[list[float]]:
    """
    批量生成文本向量。

    normalize_embeddings=True：
    对生成的向量进行归一化，使相似度排序更加稳定。
    """
    if not texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        batch_size=16,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    return embeddings.tolist()


def delete_material_vectors(material_id: int) -> None:
    """
    删除某份资料在 Chroma 中的全部旧向量。

    用于：
    1. 资料删除；
    2. 重新解析；
    3. 重新分块；
    4. 重新生成向量。
    """
    collection = get_chroma_collection()

    collection.delete(
        where={
            "material_id": material_id
        }
    )


def index_material_vectors(
    db: Session,
    *,
    material: Material
) -> int:
    """
    为某份资料的全部分块生成向量，并写入 Chroma。

    返回成功写入的分块数量。
    """

    chunks = (
        db.query(MaterialChunk)
        .filter(
            MaterialChunk.material_id == material.id,
            MaterialChunk.user_id == material.user_id
        )
        .order_by(MaterialChunk.chunk_index.asc())
        .all()
    )

    if not chunks:
        raise ValueError("该资料没有可向量化的文本分块")

    # 先清理旧向量，避免重新分块后残留旧数据
    delete_material_vectors(material.id)

    texts = [chunk.content for chunk in chunks]

    try:
        embeddings = encode_texts(texts)

        vector_ids = [
            f"chunk_{chunk.id}"
            for chunk in chunks
        ]

        metadatas = []

        for chunk in chunks:
            metadatas.append(
                {
                    "user_id": int(chunk.user_id),
                    "course_id": int(chunk.course_id),
                    "material_id": int(chunk.material_id),
                    "chunk_id": int(chunk.id),
                    "chunk_index": int(chunk.chunk_index),

                    # Chroma 元数据不保存 None，
                    # 没有页码时暂时使用 -1
                    "page_no": (
                        int(chunk.page_no)
                        if chunk.page_no is not None
                        else -1
                    )
                }
            )

        collection = get_chroma_collection()

        # upsert：存在则更新，不存在则新增
        collection.upsert(
            ids=vector_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

        for chunk, vector_id in zip(chunks, vector_ids):
            chunk.vector_id = vector_id
            chunk.vector_status = "success"

        db.commit()

        return len(chunks)

    except Exception:
        db.rollback()

        # 如果过程中失败，删除可能已经写入的部分数据
        try:
            delete_material_vectors(material.id)
        except Exception:
            pass

        (
            db.query(MaterialChunk)
            .filter(
                MaterialChunk.material_id == material.id
            )
            .update(
                {
                    MaterialChunk.vector_id: None,
                    MaterialChunk.vector_status: "failed"
                },
                synchronize_session=False
            )
        )

        db.commit()
        raise


def semantic_search(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    query: str,
    top_k: int = 5
) -> list[dict[str, Any]]:
    """
    在指定用户的指定课程中进行语义检索。
    """

    query = query.strip()

    if not query:
        raise ValueError("检索问题不能为空")

    query_embedding = encode_texts([query])[0]

    collection = get_chroma_collection()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={
            "$and": [
                {
                    "user_id": user_id
                },
                {
                    "course_id": course_id
                }
            ]
        },
        include=[
            "documents",
            "metadatas",
            "distances"
        ]
    )

    result_ids = (
        results.get("ids", [[]])[0]
        if results.get("ids")
        else []
    )

    documents = (
        results.get("documents", [[]])[0]
        if results.get("documents")
        else []
    )

    metadatas = (
        results.get("metadatas", [[]])[0]
        if results.get("metadatas")
        else []
    )

    distances = (
        results.get("distances", [[]])[0]
        if results.get("distances")
        else []
    )

    material_ids = {
        int(metadata["material_id"])
        for metadata in metadatas
        if metadata and "material_id" in metadata
    }

    materials = (
        db.query(Material)
        .filter(
            Material.id.in_(material_ids),
            Material.user_id == user_id,
            Material.course_id == course_id
        )
        .all()
        if material_ids
        else []
    )

    material_map = {
        material.id: material
        for material in materials
    }

    search_results = []

    for index, vector_id in enumerate(result_ids):
        metadata = metadatas[index] or {}
        content = documents[index] or ""
        distance = float(distances[index])

        material_id = int(metadata["material_id"])
        material = material_map.get(material_id)

        # 距离越小代表越相似。
        # 转成 0～1 范围内的展示分数。
        similarity_score = 1.0 / (1.0 + max(distance, 0.0))

        page_no = int(metadata.get("page_no", -1))

        search_results.append(
            {
                "vector_id": vector_id,
                "chunk_id": int(metadata["chunk_id"]),
                "chunk_index": int(metadata["chunk_index"]),
                "material_id": material_id,
                "material_title": (
                    material.title
                    if material
                    else "未知资料"
                ),
                "page_no": (
                    page_no
                    if page_no >= 0
                    else None
                ),
                "content": content,
                "distance": round(distance, 6),
                "similarity_score": round(
                    similarity_score,
                    4
                )
            }
        )

    return search_results