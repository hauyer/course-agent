import asyncio
from io import BytesIO

from fastapi import UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

from app.database import Base
from app.models.user import User
from app.routers.auth import delete_avatar, update_avatar


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (480, 320), (112, 132, 112)).save(output, format="PNG")
    return output.getvalue()


def test_avatar_is_resized_persisted_and_can_be_removed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'avatar.db'}")
    User.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(username="avatar-user", password_hash="hash", role="student")
    db.add(user)
    db.commit()
    db.refresh(user)

    upload = UploadFile(
        file=BytesIO(_png_bytes()),
        filename="avatar.png",
        headers=Headers({"content-type": "image/png"}),
    )
    updated = asyncio.run(update_avatar(file=upload, db=db, current_user=user))
    assert updated.avatar_data.startswith("data:image/webp;base64,")
    assert len(updated.avatar_data) < 200_000

    cleared = delete_avatar(db=db, current_user=user)
    assert cleared.avatar_data is None
    db.close()
