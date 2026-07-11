from typing import Optional

from pydantic import BaseModel, ConfigDict


class MaterialChunkResponse(BaseModel):
    id: int
    material_id: int
    course_id: int
    chunk_index: int
    page_no: Optional[int] = None
    content: str
    char_count: int
    vector_status: str

    model_config = ConfigDict(from_attributes=True)


class MaterialChunkListResponse(BaseModel):
    material_id: int
    total: int
    skip: int
    limit: int
    items: list[MaterialChunkResponse]


class RebuildChunksResponse(BaseModel):
    material_id: int
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    message: str