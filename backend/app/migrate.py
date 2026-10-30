"""Run Alembic migrations programmatically (on startup and from the CLI)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    if database_url:
        cfg.attributes["database_url"] = database_url
    return cfg


def upgrade_to_head(engine: Engine) -> None:
    cfg = alembic_config()
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # Only one process migrates at a time (e.g. two workers starting together).
            conn.exec_driver_sql("SELECT pg_advisory_xact_lock(827463183)")
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def current_and_head(engine: Engine) -> tuple[str | None, str | None]:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head
