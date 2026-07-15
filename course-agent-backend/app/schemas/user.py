#作用: 定义用户相关的Pydantic模型，用于请求和响应的数据验证和序列化。主要规定前端传什么、后端返回什么。
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class PasswordVerify(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=100)


class LlmConfigUpdate(BaseModel):
    current_password: str = Field(..., min_length=6, max_length=100)
    provider: Literal["openai", "deepseek"] = "openai"
    model_name: str = Field(..., min_length=1, max_length=120)
    base_url: Optional[str] = Field(default=None, max_length=1000)
    api_key: str = Field(..., min_length=8, max_length=1000)


class LlmConfigResponse(BaseModel):
    configured: bool
    enabled: bool
    provider: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key_hint: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    avatar_data: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
