from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MaterialResponse(BaseModel):
    id: int
    user_id: int
    course_id: int

    title: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_type: str
    mime_type: Optional[str] = None
    file_size: int
    parse_status: str
    parse_error: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaterialTextResponse(BaseModel):
    material_id: int
    title: str
    parse_status: str
    text_length: int
    text_preview: str