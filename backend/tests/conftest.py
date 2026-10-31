"""Test fixtures.

Tests run against SQLite by default. To run against PostgreSQL set
CV_TEST_DATABASE_URL=postgresql+psycopg://user@host/dbname (the database is wiped).
"""

from __future__ import annotations

import io
import os
import random
from pathlib import Path

import piexif
import pytest
from PIL import Image, ImageDraw, ImageFilter
from fastapi.testclient import TestClient
from sqlalchemy import text

TEST_DB = os.environ.get("CV_TEST_DATABASE_URL")
PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def tmp_root(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("cv")


@pytest.fixture(scope="session")
def configured(tmp_root):
    url = TEST_DB or f"sqlite:///{tmp_root / 'test.db'}"
    os.environ["CV_DATABASE_URL"] = url
    os.environ["CV_MEDIA_ROOT"] = str(tmp_root / "media")
    os.environ["CV_RUN_MIGRATIONS_ON_STARTUP"] = "false"
    os.environ["CV_LOG_JSON"] = "false"
    os.environ["CV_LOG_LEVEL"] = "WARNING"
    os.environ["CV_SCHEDULER_ENABLED"] = "false"
    os.environ["CV_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    from app.config import get_settings
    from app.db import get_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    from app.migrate import upgrade_to_head

    upgrade_to_head(engine)
    return url


TABLES = [
    "valuations",
    "spot_prices",
    "provider_configs",
    "api_quota_periods",
    "api_call_log",
    "system_settings",
    "upload_files",
    "upload_groups",
    "document_links",
    "documents",
    "item_tags",
    "item_metal_content",
    "item_condition",
    "coin_details",
    "bar_details",
    "banknote_details",
    "lot_details",
    "other_details",
    "photos",
    "items",
    "tags",
    "locations",
    "audit_log",
    "app_settings",
    "api_tokens",
    "sessions",
    "users",
]


@pytest.fixture
def app(configured):
    from app.db import get_engine
    from app.main import create_app
    from app.routers.auth import throttle

    engine = get_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("UPDATE items SET cover_photo_id = NULL"))
            # compositions references users, so TRUNCATE users CASCADE would wipe the seeded rows too.
            conn.execute(text("DELETE FROM compositions WHERE owner_id IS NOT NULL"))
            conn.execute(text(f"TRUNCATE {', '.join(t for t in TABLES if t != 'users')} RESTART IDENTITY CASCADE"))
            conn.execute(text("DELETE FROM users"))
        else:
            for t in TABLES:
                conn.execute(text(f"DELETE FROM {t}"))
            conn.execute(text("DELETE FROM compositions WHERE owner_id IS NOT NULL"))
    throttle.reset()
    return create_app()


def _make_user(username: str, admin: bool = True) -> None:
    from app.db import session_factory
    from app.models import User
    from app.security import hash_password

    with session_factory()() as db:
        db.add(User(username=username, password_hash=hash_password(PASSWORD), is_admin=admin))
        db.commit()


class Api:
    """TestClient wrapper that signs in and sends the CSRF header automatically."""

    def __init__(self, client: TestClient):
        self.c = client
        self.csrf: str | None = None

    def login(self, username: str = "admin", password: str = PASSWORD):
        r = self.c.post("/api/v1/auth/login", json={"username": username, "password": password})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
        return r

    def _h(self, headers=None):
        h = dict(headers or {})
        if self.csrf:
            h.setdefault("X-CSRF-Token", self.csrf)
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, headers=None, **kw):
        return self.c.post(url, headers=self._h(headers), **kw)

    def patch(self, url, headers=None, **kw):
        return self.c.patch(url, headers=self._h(headers), **kw)

    def put(self, url, headers=None, **kw):
        return self.c.put(url, headers=self._h(headers), **kw)

    def delete(self, url, headers=None, **kw):
        return self.c.delete(url, headers=self._h(headers), **kw)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client) -> Api:
    _make_user("admin")
    a = Api(client)
    assert a.login().status_code == 200
    return a


@pytest.fixture
def make_user():
    return _make_user


# --- Synthetic images -----------------------------------------------------------------


def coin_image(seed: int = 1, size: int = 1600, blur: float = 0.0, glare: bool = False) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", (size, size), (40, 40, 45))
    d = ImageDraw.Draw(img)
    m = size // 10
    d.ellipse([m, m, size - m, size - m], fill=(180, 180, 175))
    for _ in range(600):  # fine detail so sharpness is measurable
        x, y = rnd.randint(2 * m, size - 2 * m), rnd.randint(2 * m, size - 2 * m)
        r = rnd.randint(2, 18)
        c = rnd.randint(60, 240)
        d.ellipse([x - r, y - r, x + r, y + r], outline=(c, c, c), width=2)
    for i in range(0, size, 9):
        d.line([(i, size // 2 - 40), (i + 4, size // 2 + 40)], fill=(rnd.randint(50, 220),) * 3, width=1)
    if glare:
        d.ellipse([size // 4, size // 4, size * 3 // 4, size * 3 // 4], fill=(255, 255, 255))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img


def jpeg_bytes(img: Image.Image, gps: bool = False, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    if gps:
        exif = piexif.dump(
            {
                "0th": {piexif.ImageIFD.Make: b"TestCam", piexif.ImageIFD.Orientation: 1},
                "GPS": {
                    piexif.GPSIFD.GPSLatitudeRef: b"N",
                    piexif.GPSIFD.GPSLatitude: ((38, 1), (41, 1), (0, 1)),
                    piexif.GPSIFD.GPSLongitudeRef: b"W",
                    piexif.GPSIFD.GPSLongitude: ((75, 1), (23, 1), (0, 1)),
                },
            }
        )
        img.save(buf, "JPEG", quality=quality, exif=exif)
    else:
        img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n160\n%%EOF\n"
)


@pytest.fixture
def images():
    return {"coin": coin_image, "jpeg": jpeg_bytes, "png": png_bytes, "pdf": MINIMAL_PDF}
