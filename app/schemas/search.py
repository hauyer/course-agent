from typing import Optional

from pydantic import BaseModel, Field


class VectorIndexResponse(BaseModel):
    material_id: int
    indexed_count: int
    message: str


class SemanticSearchRequest(BaseModel):
    course_id: int

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20
    )


class SemanticSearchItem(BaseModel):
    vector_id: str
    chunk_id: int
    chunk_index: int

    material_id: int
    material_title: str

    page_no: Optional[int] = None

    content: str
    distance: float
    similarity_score: float


class SemanticSearchResponse(BaseModel):
    course_id: int
    query: str
    total: int
    results: list[SemanticSearchItem]