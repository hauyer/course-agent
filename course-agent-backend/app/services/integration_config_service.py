import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.models.integration_config import IntegrationConfig
from app.schemas.note import IntegrationConfigUpdate
from app.utils.security import SECRET_KEY


def _cipher() -> Fernet:
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("用户集成密钥无法解密，请重新保存配置") from exc


def get_integration_config(db: Session, *, user_id: int) -> IntegrationConfig | None:
    return (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.user_id == user_id)
        .first()
    )


def save_integration_config(
    db: Session,
    *,
    user_id: int,
    config_in: IntegrationConfigUpdate,
) -> IntegrationConfig:
    config = get_integration_config(db, user_id=user_id)
    if config is None:
        config = IntegrationConfig(user_id=user_id)
        db.add(config)

    data = config_in.model_dump(exclude_unset=True)
    api_key = data.pop("notion_api_key", None)
    # An empty password field means "keep the existing token" so editing the
    # Obsidian path never accidentally erases a working Notion credential.
    if api_key is not None and api_key.strip():
        config.notion_api_key_encrypted = encrypt_secret(api_key.strip())

    for key, value in data.items():
        setattr(config, key, value.strip() if isinstance(value, str) else value)

    db.commit()
    db.refresh(config)
    return config


def serialize_integration_config(config: IntegrationConfig | None) -> dict:
    if config is None:
        return {
            "notion_configured": False,
            "notion_invalid": False,
            "notion_error_message": None,
            "notion_api_key_hint": None,
            "notion_parent_page_id": None,
            "notion_api_version": "2026-03-11",
            "notion_timeout_seconds": 30,
            "obsidian_configured": False,
            "obsidian_vault_path": None,
            "obsidian_base_folder": "课程学习助手",
        }
    token = None
    notion_invalid = False
    notion_error_message = None
    try:
        token = decrypt_secret(config.notion_api_key_encrypted)
    except RuntimeError:
        notion_invalid = True
        notion_error_message = "原 Notion Token 无法解密，请重新输入 Token 后保存"
    return {
        "notion_configured": bool(token and config.notion_parent_page_id),
        "notion_invalid": notion_invalid,
        "notion_error_message": notion_error_message,
        "notion_api_key_hint": f"••••{token[-4:]}" if token else None,
        "notion_parent_page_id": config.notion_parent_page_id,
        "notion_api_version": config.notion_api_version,
        "notion_timeout_seconds": config.notion_timeout_seconds,
        "obsidian_configured": bool(config.obsidian_vault_path),
        "obsidian_vault_path": config.obsidian_vault_path,
        "obsidian_base_folder": config.obsidian_base_folder,
    }


def require_notion_runtime(config: IntegrationConfig | None) -> tuple[str, str, str, float]:
    if config is None:
        raise RuntimeError("当前用户尚未配置 Notion")
    token = decrypt_secret(config.notion_api_key_encrypted)
    if not token or not config.notion_parent_page_id:
        raise RuntimeError("当前用户的 Notion Token 或父页面 ID 未配置")
    return (
        token,
        config.notion_parent_page_id,
        config.notion_api_version,
        float(config.notion_timeout_seconds),
    )


def require_obsidian_runtime(config: IntegrationConfig | None) -> tuple[str, str]:
    if config is None or not config.obsidian_vault_path:
        raise RuntimeError("当前用户尚未配置 Obsidian Vault")
    return config.obsidian_vault_path, config.obsidian_base_folder
