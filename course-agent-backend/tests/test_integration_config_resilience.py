import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.integration_config import IntegrationConfig
from app.models.user import User
from app.schemas.note import IntegrationConfigUpdate
from app.services import integration_config_service
from app.services.integration_config_service import (
    save_integration_config,
    serialize_integration_config,
)


@pytest.fixture
def integration_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, IntegrationConfig.__table__])
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(User(id=1, username="integration-user", email="integration@example.com", password_hash="x"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_invalid_legacy_notion_token_does_not_break_configuration_page(
    integration_db, monkeypatch
):
    config = IntegrationConfig(
        user_id=1,
        notion_api_key_encrypted=integration_config_service.encrypt_secret("secret-old"),
        notion_parent_page_id="a" * 32,
        obsidian_vault_path="D:/Notes/Vault",
        obsidian_base_folder="课程学习助手",
    )
    integration_db.add(config)
    integration_db.commit()

    monkeypatch.setattr(integration_config_service, "SECRET_KEY", "rotated-test-key")
    payload = serialize_integration_config(config)

    assert payload["notion_configured"] is False
    assert payload["notion_invalid"] is True
    assert "重新输入" in payload["notion_error_message"]
    assert payload["obsidian_configured"] is True
    assert payload["obsidian_vault_path"] == "D:/Notes/Vault"


def test_reentering_notion_token_recovers_invalid_configuration(integration_db, monkeypatch):
    config = IntegrationConfig(
        user_id=1,
        notion_api_key_encrypted="invalid-token",
        notion_parent_page_id="a" * 32,
    )
    integration_db.add(config)
    integration_db.commit()
    monkeypatch.setattr(integration_config_service, "SECRET_KEY", "new-test-key")

    saved = save_integration_config(
        integration_db,
        user_id=1,
        config_in=IntegrationConfigUpdate(
            notion_api_key="secret-new",
            notion_parent_page_id="a" * 32,
        ),
    )
    payload = serialize_integration_config(saved)

    assert payload["notion_configured"] is True
    assert payload["notion_invalid"] is False
    assert payload["notion_api_key_hint"].endswith("-new")
