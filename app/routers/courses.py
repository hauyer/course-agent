from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.course import CourseCreate, CourseUpdate, CourseResponse
from app.services.auth_service import get_current_user
from app.services.course_service import (
    create_course,
    get_user_courses,
    get_course_by_id,
    update_course,
    delete_course
)

router = APIRouter()


@router.post("", response_model=CourseResponse)
def create_course_api(
    course_in: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建课程。
    """
    course = create_course(
        db=db,
        user_id=current_user.id,
        course_in=course_in
    )

    return course


@router.get("", response_model=List[CourseResponse])
def list_courses_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的课程列表。
    """
    courses = get_user_courses(
        db=db,
        user_id=current_user.id
    )

    return courses


@router.get("/{course_id}", response_model=CourseResponse)
def get_course_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取课程详情。
    """
    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    return course


@router.put("/{course_id}", response_model=CourseResponse)
def update_course_api(
    course_id: int,
    course_in: CourseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    修改课程信息。
    """
    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    course = update_course(
        db=db,
        course=course,
        course_in=course_in
    )

    return course


@router.delete("/{course_id}")
def delete_course_api(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除课程。
    """
    course = get_course_by_id(
        db=db,
        user_id=current_user.id,
        course_id=course_id
    )

    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="课程不存在或无权限访问"
        )

    delete_course(
        db=db,
        course=course
    )

    return {
        "message": "课程删除成功"
    }