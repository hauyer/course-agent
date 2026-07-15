from datetime import datetime
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


NoteType = Literal[
    "manual",
    "summary",
    "knowledge_point",
    "review",
]

NoteSource = Literal[
    "manual",
    "material",
    "agent",
]


class NoteCreate(BaseModel):
    course_id: int = Field(..., ge=1)

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    content_markdown: str = Field(
        default="",
        max_length=2_000_000,
    )

    tags: list[str] = Field(
        default_factory=list,
        max_length=50,
    )

    note_type: NoteType = "manual"
    source: NoteSource = "manual"

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        result: list[str] = []

        for tag in tags:
            normalized = tag.strip()

            if (
                normalized
                and normalized not in result
            ):
                result.append(normalized[:50])

        return result


class NoteUpdate(BaseModel):
    course_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    content_markdown: Optional[str] = Field(
        default=None,
        max_length=2_000_000,
    )

    tags: Optional[list[str]] = Field(
        default=None,
        max_length=50,
    )

    note_type: Optional[NoteType] = None
    source: Optional[NoteSource] = None

    @field_validator("tags")
    @classmethod
    def normalize_tags(
        cls,
        tags: Optional[list[str]],
    ) -> Optional[list[str]]:
        if tags is None:
            return None

        result: list[str] = []

        for tag in tags:
            normalized = tag.strip()

            if (
                normalized
                and normalized not in result
            ):
                result.append(normalized[:50])

        return result


class NoteResponse(BaseModel):
    id: int
    user_id: int
    course_id: int

    title: str
    content_markdown: str
    tags: list[str]

    note_type: str
    source: str

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class NoteListResponse(BaseModel):
    total: int
    items: list[NoteResponse]


class NoteSyncRecordResponse(BaseModel):
    id: int
    note_id: int

    provider: str
    external_id: Optional[str]
    external_path: Optional[str]

    sync_status: str
    content_hash: Optional[str]
    last_synced_at: Optional[datetime]
    last_error: Optional[str]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class ObsidianSyncResponse(BaseModel):
    note_id: int
    provider: str
    sync_status: str
    external_path: str
    content_hash: str
    last_synced_at: datetime


class ObsidianTestResponse(BaseModel):
    success: bool
    vault_path: str
    base_folder: str
    message: str

class NotionTestResponse(BaseModel):
    success: bool
    parent_page_id: str
    parent_page_title: str
    message: str


class NotionSyncResponse(BaseModel):
    note_id: int
    provider: str
    sync_status: str

    notion_page_id: str
    page_url: Optional[str]

    content_hash: str
    last_synced_at: datetime


class IntegrationConfigUpdate(BaseModel):
    notion_api_key: Optional[str] = Field(default=None, max_length=1000)
    notion_parent_page_id: Optional[str] = Field(default=None, max_length=255)
    notion_api_version: str = Field(default="2026-03-11", max_length=30)
    notion_timeout_seconds: int = Field(default=30, ge=1, le=120)
    obsidian_vault_path: Optional[str] = Field(default=None, max_length=2000)
    obsidian_base_folder: str = Field(default="课程学习助手", max_length=255)


class IntegrationConfigResponse(BaseModel):
    notion_configured: bool
    notion_invalid: bool = False
    notion_error_message: Optional[str] = None
    notion_api_key_hint: Optional[str]
    notion_parent_page_id: Optional[str]
    notion_api_version: str
    notion_timeout_seconds: int
    obsidian_configured: bool
    obsidian_vault_path: Optional[str]
    obsidian_base_folder: str
