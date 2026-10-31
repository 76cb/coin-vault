"""Application settings, read from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CV_", extra="ignore")

    # Database. Postgres in production; SQLite is fine for development and tests.
    database_url: str = "sqlite:///./coinvault.db"

    # Where photo originals, derivatives and documents live. Never inside the database.
    media_root: Path = Path("./media")

    # Session cookie
    session_cookie_name: str = "cv_session"
    session_ttl_hours: int = 24 * 14
    # Set true only when served over HTTPS (e.g. behind Caddy). Plain http on the LAN needs false.
    cookie_secure: bool = False

    # Upload limits (megabytes)
    max_photo_mb: int = 40
    max_document_mb: int = 25
    max_files_per_upload: int = 200

    # When nginx fronts the app it serves protected files itself via X-Accel-Redirect.
    use_x_accel: bool = False
    x_accel_prefix: str = "/protected-media"

    # Login throttling: failed attempts allowed per IP within the window.
    login_max_failures: int = 5
    login_window_seconds: int = 300

    run_migrations_on_startup: bool = True
    log_level: str = "INFO"
    log_json: bool = True

    # Built frontend (served by nginx in production; FastAPI serves it in dev/compose if set)
    frontend_dist: Path | None = None

    # Base64 of 32 random bytes; encrypts provider API keys at rest. The installer generates it.
    # Losing it means re-entering API keys in Settings; nothing else is affected.
    encryption_key: str | None = None

    # Background jobs (spot polling). Off in tests.
    scheduler_enabled: bool = True
    # Timezone used for market hours and the daily jobs.
    timezone: str = "America/New_York"
    http_timeout_seconds: float = 15.0

    # Backups: the folder (default: "backups" next to the media folder, /var/lib/coinvault/backups on the LXC).
    # Point it at a mounted NAS or second disk to keep backups off the container's own disk.
    backup_dir: Path | None = None
    # Folder of pg_dump / pg_restore matching the server (default: whatever is on PATH).
    pg_bin: Path | None = None

    # Duplicate detection threshold (pHash Hamming distance)
    phash_duplicate_distance: int = Field(default=6, ge=0, le=64)


@lru_cache
def get_settings() -> Settings:
    return Settings()
