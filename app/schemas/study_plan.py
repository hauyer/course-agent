from datetime import date, datetime, time
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.task import TaskResponse


StudyPlanStatus = Literal[
    "draft",
    "active",
    "completed",
    "cancelled",
]

TaskPriority = Literal[
    "low",
    "medium",
    "high",
    "urgent",
]


class StudyPlanCreate(BaseModel):
    course_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    goal: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    start_date: date
    end_date: date

    daily_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
    )

    status: StudyPlanStatus = "draft"

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("计划结束日期不能早于开始日期")

        return self


class StudyPlanUpdate(BaseModel):
    course_id: Optional[int] = Field(
        default=None,
        ge=1,
    )

    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    goal: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    daily_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=1440,
    )

    status: Optional[StudyPlanStatus] = None


class StudyPlanStatusUpdate(BaseModel):
    status: StudyPlanStatus


class StudyPlanResponse(BaseModel):
    id: int
    user_id: int
    course_id: Optional[int]

    title: str
    goal: Optional[str]

    start_date: date
    end_date: date
    daily_minutes: int
    status: str

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudyPlanListResponse(BaseModel):
    total: int
    items: list[StudyPlanResponse]


class StudyPlanTaskCreate(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=5000,
    )

    planned_date: date

    due_time: Optional[time] = Field(
        default=None,
        description="当天截止时间，不传时默认为 23:59:59",
    )

    sequence_no: int = Field(
        default=1,
        ge=1,
        le=1000,
    )

    priority: TaskPriority = "medium"

    estimated_minutes: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000,
    )

    parent_task_id: Optional[int] = Field(
        default=None,
        ge=1,
    )


class StudyPlanTaskResponse(BaseModel):
    id: int
    study_plan_id: int
    task_id: int
    planned_date: date
    sequence_no: int
    task: TaskResponse


class StudyPlanTaskListResponse(BaseModel):
    total: int
    items: list[StudyPlanTaskResponse]


class StudyPlanProgressResponse(BaseModel):
    study_plan_id: int

    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    cancelled_tasks: int
    overdue_tasks: int

    estimated_total_minutes: int
    completed_estimated_minutes: int

    progress_percent: float