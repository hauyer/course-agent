
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    teacher: Optional[str] = None
    semester: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    teacher: Optional[str] = None
    semester: Optional[str] = None


class CourseResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    teacher: Optional[str] = None
    semester: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)