"""Backups: made, checked, rotated, downloaded, and put back (database and files) on SQLite and PostgreSQL."""

import datetime as dt
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from app.services import backup

from .test_photos import make_item, upload


@pytest.fixture(autouse=True)
def _empty_backup_folder(app):
    shutil.rmtree(backup.backup_root(), ignore_errors=True)
    yield
    shutil.rmtree(backup.backup_root(), ignore_errors=True)


def _settings():
    from app.config import get_settings

    return get_settings()


def _restore(source):
    """What `python -m app.cli restore` does, with the app's connections closed first (as when the service is stopped)."""
    from app.db import get_engine
    from app.migrate import upgrade_to_head

    s = _settings()
    get_engine().dispose()
    manifest = backup.restore(Path(source), s.database_url, Path(s.media_root).resolve())
    get_engine().dispose()
    upgrade_to_head(get_engine())
    return manifest


def test_backup_and_restore(api, images):
    item = make_item(api, "Backed up Morgan")
    photo = upload(api, item["id"], [("m.jpg", images["jpeg"](images["coin"](seed=41)), "image/jpeg")]).json()[0]
    api.post(f"/api/v1/items/{item['id']}/valuations", json={"kind": "manual", "value_each": "77"})

    r = api.post("/api/v1/backups")
    assert r.status_code == 201, r.text
    made = r.json()
    assert made["counts"]["items"] >= 1 and made["counts"]["photos"] >= 1 and made["verified"]
    root = backup.backup_root()
    original_key = next(rel for rel, _ in json.loads((root / made["name"] / "manifest.json").read_text())["files"] if rel.startswith("originals/"))

    # the collection gets damaged: the item and its photo file are gone
    assert api.delete(f"/api/v1/items/{item['id']}?purge=true").status_code in (204, 200)
    media = Path(_settings().media_root).resolve()
    shutil.rmtree(media / "originals")
    assert api.get(f"/api/v1/items/{item['id']}").status_code == 404 or api.get(f"/api/v1/items/{item['id']}").json().get("deleted_at")

    _restore(root / made["name"])
    back = api.get(f"/api/v1/items/{item['id']}")
    assert back.status_code == 200 and back.json()["title"] == "Backed up Morgan" and not back.json()["deleted_at"]
    assert (media / original_key).exists()
    assert api.get(photo["urls"]["original"]).status_code == 200
    assert api.get(f"/api/v1/items/{item['id']}/valuations").json()[0]["value_each"].startswith("77")


def test_download_is_a_restorable_archive(api, images, tmp_path):
    item = make_item(api, "Archived")
    upload(api, item["id"], [("a.jpg", images["jpeg"](images["coin"](seed=42)), "image/jpeg")])
    made = api.post("/api/v1/backups").json()
    r = api.get(f"/api/v1/backups/{made['name']}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/x-tar"
    assert f'coinvault-backup-{made["name"]}.tar' in r.headers["content-disposition"]
    tar_path = tmp_path / "b.tar"
    tar_path.write_bytes(r.content)
    with tarfile.open(tar_path) as tar:
        names = tar.getnames()
    assert f"{made['name']}/manifest.json" in names and any("/files/originals/" in n for n in names)

    api.delete(f"/api/v1/items/{item['id']}?purge=true")
    shutil.rmtree(backup.backup_root())  # the server's backups are lost too: only the download is left
    _restore(tar_path)
    assert api.get(f"/api/v1/items/{item['id']}").json()["title"] == "Archived"


def test_status_settings_and_delete(api):
    st = api.get("/api/v1/backups").json()
    assert st["enabled"] is True and st["time"] == "03:15" and st["backups"] == [] and st["folder"]
    assert api.put("/api/v1/backups/settings", json={"enabled": False, "time": "02:30"}).json()["time"] == "02:30"
    assert api.put("/api/v1/backups/settings", json={"enabled": True, "time": "25:00"}).status_code == 422
    made = api.post("/api/v1/backups").json()
    st = api.get("/api/v1/backups").json()
    assert st["last"]["ok"] and st["last"]["name"] == made["name"] and len(st["backups"]) == 1
    assert api.delete(f"/api/v1/backups/{made['name']}").status_code == 204
    assert api.get("/api/v1/backups").json()["backups"] == []
    assert api.delete("/api/v1/backups/../etc").status_code in (404, 405)


def test_bad_backups_are_refused(api, tmp_path):
    made = api.post("/api/v1/backups").json()
    folder = backup.backup_root() / made["name"]
    db_file = next(folder.glob("database.*"))
    db_file.write_bytes(db_file.read_bytes()[:-10] + b"0123456789")
    with pytest.raises(backup.BackupError, match="damaged"):
        backup.restore(folder, _settings().database_url, tmp_path / "media")


def test_rotation():
    now = dt.datetime(2026, 10, 31, 12, tzinfo=dt.UTC)

    def info(days_ago, hour=3):
        t = now - dt.timedelta(days=days_ago, hours=12 - hour)
        return backup.BackupInfo(t.strftime(backup.NAME_FORMAT), Path("/x"), {"created_at": t.isoformat()})

    nightly = [info(d) for d in range(0, 400)]
    extra_today = [info(0, 10), info(0, 11)]
    bs = sorted(extra_today + nightly, key=lambda b: b.created_at, reverse=True)
    keep = backup.keep_set(bs, now)
    kept_days = sorted({(now - b.created_at).days for b in bs if b.name in keep})
    assert all(d in kept_days for d in range(0, 7))  # every day this week
    assert len(keep) <= 3 + 7 + 5 + 13 and len(keep) >= 15
    assert max(kept_days) <= 366 and max(kept_days) > 300  # monthly copies reach back about a year
    assert all(b.name in keep for b in bs[:3])  # the newest three always stay


def test_admin_only(api, app, make_user):
    from fastapi.testclient import TestClient

    from tests.conftest import Api

    with TestClient(app) as c:
        make_user("viewer", admin=False)
        other = Api(c)
        other.login("viewer")
        assert other.get("/api/v1/backups").status_code == 403
        assert other.post("/api/v1/backups").status_code == 403


def test_archive_stream_chunks(api, images):
    item = make_item(api, "Chunks")
    upload(api, item["id"], [("c.jpg", images["jpeg"](images["coin"](seed=43)), "image/jpeg")])
    made = api.post("/api/v1/backups").json()
    b = backup.get_backup(made["name"])
    data = b"".join(backup.archive_stream(b))
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        assert len([m for m in tar.getmembers() if m.isfile()]) == len(b.manifest["files"]) + 2


def test_command_line_backup_and_restore(tmp_path):
    """The commands restore.sh and update.sh run, in a separate process against a fresh install."""
    import os
    import subprocess
    import sys

    backend = Path(__file__).resolve().parent.parent
    env = {**os.environ, "CV_DATABASE_URL": f"sqlite:///{tmp_path}/cv.db", "CV_MEDIA_ROOT": str(tmp_path / "media"),
           "CV_LOG_JSON": "false", "CV_SCHEDULER_ENABLED": "false"}
    env.pop("CV_BACKUP_DIR", None)

    def cli(*args, stdin=None):
        r = subprocess.run([sys.executable, "-m", "app.cli", *args], cwd=backend, env=env, input=stdin,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout

    cli("create-admin", "--username", "first", "--password-stdin", stdin="a-long-password-1\n")
    (tmp_path / "media" / "originals" / "ab").mkdir(parents=True)
    (tmp_path / "media" / "originals" / "ab" / "photo.jpg").write_bytes(b"jpeg bytes")
    out = cli("backup")
    assert "Backup " in out and "1 files" in out
    name = cli("list-backups").split()[0]

    (tmp_path / "cv.db").unlink()  # disaster
    shutil.rmtree(tmp_path / "media")
    out = cli("restore", name, "--yes")
    assert "Restored the backup" in out
    assert (tmp_path / "media" / "originals" / "ab" / "photo.jpg").read_bytes() == b"jpeg bytes"
    # the restored database has the user (create-admin refuses a name that exists)
    r = subprocess.run([sys.executable, "-m", "app.cli", "create-admin", "--username", "first", "--password-stdin"],
                       cwd=backend, env=env, input="another-password-2\n", capture_output=True, text=True, timeout=120)
    assert r.returncode != 0 and "already exists" in (r.stdout + r.stderr)
