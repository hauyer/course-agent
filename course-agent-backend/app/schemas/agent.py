from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentChatRequest(BaseModel):
    course_id: int = Field(..., ge=1)

    session_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="已有会话 ID；为空时自动创建新会话",
    )

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
    )


class AgentCitationItem(BaseModel):
    citation_id: str
    index: int
    course_id: int
    course_name: str
    material_id: int
    material_title: str
    chunk_id: int
    chunk_index: int
    page_no: Optional[int] = None
    content: str
    similarity_score: float


class AgentChatResponse(BaseModel):
    session_id: int
    course_id: int
    user_message_id: int
    assistant_message_id: int
    answer: str
    citations: list[AgentCitationItem]
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionResponse(BaseModel):
    id: int
    course_id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    # citations 只保存经过权限校验的资料引用。
    citations: Optional[list[dict[str, Any]]] = None
    agent_trace: Optional[list[dict[str, Any]]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
