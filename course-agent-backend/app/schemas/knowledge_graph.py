from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


GraphJobStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
]
RelationType = Literal[
    "prerequisite",
    "contains",
    "part_of",
    "related_to",
    "contrast",
    "applies_to",
]


_SCORE_WORDS = {
    "very_high": 0.95,
    "very high": 0.95,
    "high": 0.85,
    "medium": 0.6,
    "moderate": 0.6,
    "low": 0.35,
    "very_low": 0.15,
    "very low": 0.15,
    "高": 0.85,
    "中": 0.6,
    "低": 0.35,
}


def _coerce_unit_score(value, default: float = 0.5) -> float:
    """Accept common LLM score formats while keeping the stored range strict."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in _SCORE_WORDS:
            return _SCORE_WORDS[text]
        is_percent = text.endswith("%")
        if is_percent:
            text = text[:-1].strip()
        try:
            number = float(text)
        except ValueError:
            return default
        if is_percent or 1 < number <= 100:
            number /= 100
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if 1 < number <= 100:
            number /= 100
    return max(0.0, min(1.0, number))


class KnowledgeGraphJobResponse(BaseModel):
    id: int
    user_id: int
    course_id: int
    status: GraphJobStatus
    progress: int
    stage: str
    source_hash: str | None = None
    is_active: bool
    node_count: int
    edge_count: int
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeGraphSourceResponse(BaseModel):
    course_id: int
    course_name: str
    material_id: int
    material_title: str
    chunk_id: int
    chunk_index: int
    page_no: int | None = None
    evidence_text: str


class KnowledgeNodeResponse(BaseModel):
    id: int
    name: str
    node_type: str
    description: str | None = None
    importance: float
    confidence: float
    sources: list[KnowledgeGraphSourceResponse]


class KnowledgeEdgeResponse(BaseModel):
    id: int
    source: int
    target: int
    relation_type: RelationType
    weight: float
    confidence: float
    sources: list[KnowledgeGraphSourceResponse]


class KnowledgeGraphResponse(BaseModel):
    course_id: int
    course_name: str
    job_id: int
    generated_at: datetime
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]


class KnowledgeGraphVersionsResponse(BaseModel):
    total: int
    items: list[KnowledgeGraphJobResponse]


class ExtractedKnowledgeNode(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    node_type: str = Field(default="concept", min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=1500)
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    chunk_ids: list[int] = Field(..., min_length=1, max_length=20)

    @field_validator("importance", "confidence", mode="before")
    @classmethod
    def normalize_score(cls, value):
        return _coerce_unit_score(value)

    @field_validator("name", "node_type")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("知识点名称和类型不能为空")
        return value


class ExtractedKnowledgeEdge(BaseModel):
    source: str = Field(..., min_length=1, max_length=200)
    target: str = Field(..., min_length=1, max_length=200)
    relation_type: str = Field(..., min_length=1, max_length=30)
    weight: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    chunk_ids: list[int] = Field(..., min_length=1, max_length=20)

    @field_validator("weight", "confidence", mode="before")
    @classmethod
    def normalize_score(cls, value):
        return _coerce_unit_score(value)


class KnowledgeExtractionBatch(BaseModel):
    nodes: list[ExtractedKnowledgeNode] = Field(default_factory=list, max_length=100)
    edges: list[ExtractedKnowledgeEdge] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def cap_total_items(self):
        if len(self.nodes) + len(self.edges) > 250:
            raise ValueError("单批知识图谱结果过大")
        return self
