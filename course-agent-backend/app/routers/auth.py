#作用: 处理用户认证和授权相关的路由，包括注册、登录和获取当前用户信息。

import base64
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    LlmConfigResponse,
    LlmConfigUpdate,
    PasswordChange,
    PasswordVerify,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import (
    change_user_password,
    get_user_by_username,
    get_user_by_email,
    create_user,
    authenticate_user,
    get_current_user
)
from app.utils.security import create_access_token
from app.services.llm_config_service import (
    disable_llm_config,
    get_llm_config,
    save_llm_config,
    serialize_llm_config,
    verify_current_password,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册。
    """

    existing_user = get_user_by_username(db, user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    if user_in.email:
        existing_email = get_user_by_email(db, user_in.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册"
            )

    user = create_user(db, user_in)

    return user


@router.post("/login", response_model=TokenResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录。
    """

    user = authenticate_user(
        db=db,
        username=user_in.username,
        password=user_in.password
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/token")
def swagger_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    供 Swagger OAuth2 授权窗口使用。
    接收表单格式的用户名和密码。
    """

    user = authenticate_user(
        db=db,
        username=form_data.username,
        password=form_data.password
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息。
    """

    return current_user


@router.put("/avatar", response_model=UserResponse)
async def update_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存当前用户头像，并统一压缩为小尺寸 WebP。"""
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="仅支持 JPEG、PNG 或 WebP 图片")

    raw = await file.read(4 * 1024 * 1024 + 1)
    await file.close()
    if not raw:
        raise HTTPException(status_code=400, detail="头像文件不能为空")
    if len(raw) > 4 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="头像文件不能超过 4 MB")

    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=84, method=4)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=400, detail="头像图片无法解析或尺寸异常") from exc

    current_user.avatar_data = (
        "data:image/webp;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    )
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/avatar", response_model=UserResponse)
def delete_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.avatar_data = None
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/password")
def change_password(
    password_in: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        change_user_password(
            db,
            user=current_user,
            current_password=password_in.current_password,
            new_password=password_in.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"message": "密码修改成功"}


@router.post("/password/verify")
def verify_password_again(
    password_in: PasswordVerify,
    current_user: User = Depends(get_current_user),
):
    try:
        verify_current_password(
            user=current_user,
            current_password=password_in.current_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"verified": True}


@router.get("/llm-config", response_model=LlmConfigResponse)
def read_llm_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return serialize_llm_config(get_llm_config(db, user_id=current_user.id))


@router.put("/llm-config", response_model=LlmConfigResponse)
def update_llm_config(
    config_in: LlmConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        config = save_llm_config(
            db,
            user=current_user,
            current_password=config_in.current_password,
            provider=config_in.provider,
            model_name=config_in.model_name,
            base_url=config_in.base_url,
            api_key=config_in.api_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return serialize_llm_config(config)


@router.delete("/llm-config")
def remove_llm_config(
    password_in: PasswordVerify,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        disable_llm_config(
            db,
            user=current_user,
            current_password=password_in.current_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"message": "已恢复使用系统默认模型"}
