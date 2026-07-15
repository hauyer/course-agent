from pathlib import Path
import sys
from threading import Lock

from alembic import command
from alembic.config import Config

from app.database import DATABASE_URL

_migration_lock = Lock()
_migrated = False


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def run_database_migrations() -> None:
    """Apply additive migrations once per process before serving requests."""
    global _migrated
    if _migrated:
        return
    with _migration_lock:
        if _migrated:
            return
        root = _bundle_root()
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
        command.upgrade(config, "head")
        _migrated = True
