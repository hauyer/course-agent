from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from sqlalchemy import func
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.material import Material  # noqa: E402
from app.models.material_chunk import MaterialChunk  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.vector_service import (  # noqa: E402
    DEFAULT_COSINE_COLLECTION,
    LEGACY_COLLECTION_NAME,
    embedding_version,
    encode_texts,
    get_chroma_collection,
)


logger = logging.getLogger("cosine-vector-rebuild")


@dataclass
class RebuildStats:
    dry_run: bool
    eligible: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    batches: int = 0
    failed_chunk_ids: list[int] | None = None

    def __post_init__(self) -> None:
        if self.failed_chunk_ids is None:
            self.failed_chunk_ids = []


def eligible_chunk_query(db: Session):
    """Select intact SQL-owned chunks without trusting old vector_status."""

    return (
        db.query(MaterialChunk, Material)
        .join(Material, Material.id == MaterialChunk.material_id)
        .join(Course, Course.id == MaterialChunk.course_id)
        .join(User, User.id == MaterialChunk.user_id)
        .filter(
            Material.user_id == MaterialChunk.user_id,
            Material.course_id == MaterialChunk.course_id,
            Course.user_id == MaterialChunk.user_id,
            Material.parse_status == "success",
            MaterialChunk.content.isnot(None),
            func.length(func.trim(MaterialChunk.content)) > 0,
        )
    )


def iter_eligible_batches(db: Session, *, batch_size: int) -> Iterator[list[tuple[MaterialChunk, Material]]]:
    last_id = 0
    while True:
        rows = (
            eligible_chunk_query(db)
            .filter(MaterialChunk.id > last_id)
            .order_by(MaterialChunk.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            return
        yield rows
        last_id = rows[-1][0].id


def chunk_metadata(chunk: MaterialChunk, material: Material, version: str) -> dict[str, Any]:
    return {
        "user_id": int(chunk.user_id),
        "course_id": int(chunk.course_id),
        "material_id": int(chunk.material_id),
        "chunk_id": int(chunk.id),
        "chunk_index": int(chunk.chunk_index),
        "page_no": int(chunk.page_no) if chunk.page_no is not None else -1,
        "file_type": material.file_type or "unknown",
        "embedding_version": version,
    }


def rebuild_cosine_vectors(
    db: Session,
    *,
    collection: Any | None,
    dry_run: bool,
    batch_size: int = 64,
    encode_fn: Callable[[list[str]], list[list[float]]] = encode_texts,
    version: str | None = None,
) -> RebuildStats:
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size 必须在 1 到 1000 之间")
    if not dry_run and collection is None:
        raise ValueError("实际重建必须提供目标 cosine collection")

    stats = RebuildStats(dry_run=dry_run)
    if dry_run:
        stats.eligible = eligible_chunk_query(db).count()
        stats.skipped = stats.eligible
        return stats

    embedding_id = version or embedding_version()
    for rows in iter_eligible_batches(db, batch_size=batch_size):
        stats.batches += 1
        stats.eligible += len(rows)
        chunk_ids = [chunk.id for chunk, _material in rows]
        try:
            texts = [chunk.content for chunk, _material in rows]
            vectors = encode_fn(texts)
            collection.upsert(
                ids=[f"chunk_{chunk.id}" for chunk, _material in rows],
                embeddings=vectors,
                documents=texts,
                metadatas=[
                    chunk_metadata(chunk, material, embedding_id)
                    for chunk, material in rows
                ],
            )
            for chunk, _material in rows:
                chunk.vector_id = f"chunk_{chunk.id}"
                chunk.vector_status = "success"
            db.commit()
            stats.succeeded += len(rows)
        except Exception as exc:
            db.rollback()
            stats.failed += len(rows)
            stats.failed_chunk_ids.extend(chunk_ids)
            logger.error(
                "batch failed: first_chunk_id=%s count=%s error=%s",
                chunk_ids[0],
                len(chunk_ids),
                type(exc).__name__,
            )
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely rebuild SQL chunks into a separate cosine Chroma collection."
    )
    parser.add_argument("--apply", action="store_true", help="perform writes; default is dry-run")
    parser.add_argument("--yes", action="store_true", help="confirm the write operation")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--collection", default=DEFAULT_COSINE_COLLECTION)
    parser.add_argument("--legacy-collection", default=LEGACY_COLLECTION_NAME)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.apply and not args.yes:
        print("拒绝写入：使用 --apply --yes 明确确认；默认仅 dry-run。", file=sys.stderr)
        return 2
    if args.collection == args.legacy_collection:
        print("拒绝写入或检查旧 1.0 collection；请指定独立的 1.1 cosine 名称。", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        collection = None if not args.apply else get_chroma_collection(collection_name=args.collection)
        stats = rebuild_cosine_vectors(
            db,
            collection=collection,
            dry_run=not args.apply,
            batch_size=args.batch_size,
        )
        print(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
        return 1 if stats.failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

