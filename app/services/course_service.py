from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.course import Course
from app.schemas.course import CourseCreate, CourseUpdate


def create_course(
    db: Session,
    user_id: int,
    course_in: CourseCreate
) -> Course:
    """
    创建课程。
    """
    course = Course(
        user_id=user_id,
        name=course_in.name,
        description=course_in.description,
        teacher=course_in.teacher,
        semester=course_in.semester
    )

    db.add(course)
    db.commit()
    db.refresh(course)

    return course


def get_user_courses(
    db: Session,
    user_id: int
) -> List[Course]:
    """
    查询当前用户创建的所有课程。
    """
    return (
        db.query(Course)
        .filter(Course.user_id == user_id)
        .order_by(Course.created_at.desc())
        .all()
    )


def get_course_by_id(
    db: Session,
    user_id: int,
    course_id: int
) -> Optional[Course]:
    """
    查询某个课程。
    注意必须限制 user_id，防止用户访问别人的课程。
    """
    return (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.user_id == user_id
        )
        .first()
    )


def update_course(
    db: Session,
    course: Course,
    course_in: CourseUpdate
) -> Course:
    """
    修改课程信息。
    """
    update_data = course_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(course, field, value)

    db.commit()
    db.refresh(course)

    return course


def delete_course(
    db: Session,
    course: Course
) -> None:
    """
    删除课程。
    当前阶段先物理删除。
    后期如果关联了资料、对话、任务，可以改成逻辑删除。
    """
    db.delete(course)
    db.commit()