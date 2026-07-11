from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "cancelled",
]

TaskPriority = Literal[
    "low",
    "medium",
    "high",
    "urgent",
]

TaskSource = Literal[
    "manual",
    "study_plan",
    "agent",
]


class TaskCreate(BaseModel):
    course_id: Optional[int] = Field(default=None, ge=1)
    parent_task_id: Optional[int] = Field(default=None, ge=1)

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    priority: TaskPriority = "medium"
    due_at: Optional[datetime] = None

    estimated_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000,
    )

    source: TaskSource = "manual"


class TaskUpdate(BaseModel):
    course_id: Optional[int] = Field(default=None, ge=1)
    parent_task_id: Optional[int] = Field(default=None, ge=1)

    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_at: Optional[datetime] = None

    estimated_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000,
    )


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskResponse(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int]
    parent_task_id: Optional[int]

    title: str
    description: Optional[str]

    status: str
    priority: str
    due_at: Optional[datetime]
    estimated_minutes: Optional[int]
    source: str

    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


class TaskOverviewResponse(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int
    cancelled: int
    overdue: int