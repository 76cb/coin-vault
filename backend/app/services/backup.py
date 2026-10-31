"""Backups and restore.

Layout of the backup folder (CV_BACKUP_DIR, default /var/lib/coinvault/backups):

    files/<same path as under the media folder>   one copy of every photo, document and display copy,
                                                  shared by all backups (files never change once stored)
    2026-10-31T071500Z/
        manifest.json     what's in this backup: database file, every media file with its size, counts
        database.dump     PostgreSQL (pg_dump custom format)   or   database.sqlite (SQLite)

A backup is the database at that moment plus the media files it lists. Old backups are pruned by a
rotation (newest few, one a day for a week, one a week for a month, one a month for a year); a file in
files/ is removed once no remaining backup lists it.

Not included, on purpose: the settings file with CV_ENCRYPTION_KEY and the database password. Keep a copy of
/etc/coinvault/coinvault.env somewhere safe; without it, saved provider API keys can't be read after a restore
(the rest of the collection restores fine, and the keys can be entered again).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.logging_setup import log

FORMAT = 1
NAME_FORMAT = "%Y-%m-%dT%H%M%SZ"


class BackupError(RuntimeError):
    pass


def backup_root() -> Path:
    s = get_settings()
    root = Path(s.backup_dir) if s.backup_dir else Path(s.media_root).resolve().parent / "backups"
    return root


def _files_dir() -> Path:
    return backup_root() / "files"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# --- database ------------------------------------------------------------------------------


def _tool(name: str) -> str:
    """pg_dump or pg_restore: from CV_PG_BIN if set, else from PATH."""
    s = get_settings()
    path = str(Path(s.pg_bin) / name) if s.pg_bin else shutil.which(name)
    if not path or not Path(path).exists():
        raise BackupError(f"{name} isn't installed (it comes with PostgreSQL's client tools)")
    return path


def _pg_env(url: str) -> tuple[list[str], dict]:
    """Connection arguments and environment for pg_dump / pg_restore from the app's database URL."""
    u = make_url(url)
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = u.password
    args = ["--dbname", u.database or ""]
    host = u.host or u.query.get("host")
    if host:
        args += ["--host", str(host)]
    port = u.port or u.query.get("port")
    if port:
        args += ["--port", str(port)]
    if u.username:
        args += ["--username", u.username]
    return args, env


def _sqlite_path(url: str) -> Path:
    db = make_url(url).database
    if not db or db == ":memory:":
        raise BackupError("An in-memory database can't be backed up")
    return Path(db).resolve()


def dump_database(url: str, dest_dir: Path) -> Path:
    if url.startswith("postgresql"):
        out = dest_dir / "database.dump"
        args, env = _pg_env(url)
        r = subprocess.run([_tool("pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(out), *args],
                           env=env, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise BackupError(f"pg_dump failed: {r.stderr.strip()[:400]}")
        return out
    if url.startswith("sqlite"):
        out = dest_dir / "database.sqlite"
        src = sqlite3.connect(str(_sqlite_path(url)))
        dst = sqlite3.connect(str(out))
        try:
            src.backup(dst)  # a consistent copy even while the app is writing
        finally:
            dst.close()
            src.close()
        return out
    raise BackupError(f"Don't know how to back up {make_url(url).drivername}")


def check_database_file(path: Path) -> None:
    if path.suffix == ".sqlite":
        con = sqlite3.connect(str(path))
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("The database copy failed SQLite's integrity check")
        finally:
            con.close()
    else:
        r = subprocess.run([_tool("pg_restore"), "--list", str(path)], capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or "TABLE DATA" not in r.stdout:
            raise BackupError(f"pg_restore can't read the dump: {r.stderr.strip()[:300]}")


# --- media -----------------------------------------------------------------------------------


def media_files(media_root: Path) -> Iterator[tuple[str, int]]:
    """Every stored file under the media folder: (path relative to it, size). Half-written temp files are skipped."""
    if not media_root.exists():
        return
    for p in sorted(media_root.rglob("*")):
        if p.is_file() and not p.name.startswith(".tmp-"):
            yield p.relative_to(media_root).as_posix(), p.stat().st_size


def _store(src: Path, dest: Path) -> bool:
    """Put a copy of src at dest unless an identical-size one is there. Returns True if it copied."""
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".tmp-{dest.name}")
    try:
        os.link(src, tmp)  # same disk: no extra space (stored files are never changed in place)
    except OSError:
        shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    return True


# --- backups ----------------------------------------------------------------------------------


@dataclass
class BackupInfo:
    name: str
    path: Path
    manifest: dict

    @property
    def created_at(self) -> dt.datetime:
        return dt.datetime.fromisoformat(self.manifest["created_at"])


def list_backups() -> list[BackupInfo]:
    root = backup_root()
    out = []
    if root.exists():
        for d in root.iterdir():
            m = d / "manifest.json"
            if d.is_dir() and d.name != "files" and m.exists():
                try:
                    out.append(BackupInfo(d.name, d, json.loads(m.read_text())))
                except (OSError, ValueError):
                    log.warning("backup_manifest_unreadable", backup=d.name)
    return sorted(out, key=lambda b: b.created_at, reverse=True)


def get_backup(name: str) -> BackupInfo:
    if not name or "/" in name or "\\" in name or name.startswith(".") or name == "files":
        raise BackupError("No such backup")
    for b in list_backups():
        if b.name == name:
            return b
    raise BackupError("No such backup")


def _counts(db) -> dict:
    from app.models import Document, Item, Photo, User, Valuation

    return {
        "items": db.scalar(select(func.count()).select_from(Item)) or 0,
        "photos": db.scalar(select(func.count()).select_from(Photo)) or 0,
        "documents": db.scalar(select(func.count()).select_from(Document)) or 0,
        "valuations": db.scalar(select(func.count()).select_from(Valuation)) or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
    }


def run_backup(db, reason: str = "manual", now: dt.datetime | None = None) -> BackupInfo:
    """Make a backup now, check it, then prune old ones. Raises BackupError if it can't be made."""
    from app.migrate import current_and_head
    from app.db import get_engine

    s = get_settings()
    started = time.monotonic()
    now = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)
    root = backup_root()
    root.mkdir(parents=True, exist_ok=True)
    name = now.strftime(NAME_FORMAT)
    n = 1
    while (root / name).exists():  # two in the same second
        n += 1
        name = f"{now.strftime(NAME_FORMAT)}-{n}"
    dest = root / name
    work = Path(tempfile.mkdtemp(prefix=".tmp-", dir=root))
    try:
        counts = _counts(db)
        revision, _ = current_and_head(get_engine())
        db_file = dump_database(s.database_url, work)
        check_database_file(db_file)
        media_root = Path(s.media_root).resolve()
        files: list[list] = []
        copied = copied_bytes = 0
        for rel, size in media_files(media_root):
            if _store(media_root / rel, _files_dir() / rel):
                copied += 1
                copied_bytes += size
            files.append([rel, size])
        for rel, size in files:  # every listed file is really there, at the right size
            f = _files_dir() / rel
            if not f.exists() or f.stat().st_size != size:
                raise BackupError(f"The copy of {rel} is missing or incomplete")
        manifest = {
            "format": FORMAT,
            "created_at": now.isoformat(),
            "reason": reason,
            "database": {"kind": "postgresql" if db_file.suffix == ".dump" else "sqlite", "file": db_file.name,
                         "size": db_file.stat().st_size, "sha256": _sha256(db_file)},
            "revision": revision,
            "counts": counts,
            "files": files,
            "media_bytes": sum(size for _, size in files),
            "new_files": copied,
            "new_bytes": copied_bytes,
            "verified": True,
            "seconds": round(time.monotonic() - started, 1),
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=1))
        os.replace(work, dest)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    info = BackupInfo(name, dest, manifest)
    prune()
    log.info("backup_made", backup=name, reason=reason, files=len(files), new_files=copied, seconds=manifest["seconds"])
    return info


def keep_set(backups: list[BackupInfo], now: dt.datetime | None = None) -> set[str]:
    """Names to keep: the newest 3, the newest each day for 7 days, each ISO week for 4 weeks, each month for 12."""
    now = now or dt.datetime.now(dt.UTC)
    keep = {b.name for b in backups[:3]}
    seen: set[tuple] = set()
    for b in backups:  # newest first, so the first seen in each period is its newest
        age = now - b.created_at
        c = b.created_at
        for period, limit in ((("d", c.date()), dt.timedelta(days=7)),
                              (("w", *c.isocalendar()[:2]), dt.timedelta(weeks=4)),
                              (("m", c.year, c.month), dt.timedelta(days=366))):
            if age <= limit and period not in seen:
                seen.add(period)
                keep.add(b.name)
    return keep


def prune(now: dt.datetime | None = None) -> list[str]:
    """Delete backups outside the rotation, then stored files no remaining backup lists."""
    backups = list_backups()
    keep = keep_set(backups, now)
    removed = []
    for b in backups:
        if b.name not in keep:
            shutil.rmtree(b.path, ignore_errors=True)
            removed.append(b.name)
    remove_unlisted_files()
    root = backup_root()
    for leftover in root.glob(".tmp-*") if root.exists() else []:  # an interrupted backup
        if leftover.is_dir() and time.time() - leftover.stat().st_mtime > 6 * 3600:
            shutil.rmtree(leftover, ignore_errors=True)
    return removed


def remove_unlisted_files() -> int:
    listed = {rel for b in list_backups() for rel, _ in b.manifest.get("files", [])}
    files_dir = _files_dir()
    n = 0
    if files_dir.exists():
        for p in files_dir.rglob("*"):
            if p.is_file() and p.relative_to(files_dir).as_posix() not in listed:
                p.unlink(missing_ok=True)
                n += 1
    return n


def delete_backup(name: str) -> None:
    b = get_backup(name)
    shutil.rmtree(b.path)
    remove_unlisted_files()


def disk_free(path: Path | None = None) -> int | None:
    p = path or backup_root()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


# --- one-file copy (download) ---------------------------------------------------------------


class _Chunks:
    """A write-only file that hands its bytes back in pieces, for streaming a tar archive."""

    def __init__(self):
        self.parts: list[bytes] = []

    def write(self, b: bytes) -> int:
        self.parts.append(bytes(b))
        return len(b)

    def take(self) -> bytes:
        out = b"".join(self.parts)
        self.parts.clear()
        return out


def archive_stream(b: BackupInfo) -> Iterator[bytes]:
    """The backup as one .tar: manifest.json, the database file and files/... (photos are already compressed)."""
    sink = _Chunks()
    with tarfile.open(fileobj=sink, mode="w|", format=tarfile.PAX_FORMAT) as tar:
        tar.add(b.path / "manifest.json", arcname=f"{b.name}/manifest.json")
        tar.add(b.path / b.manifest["database"]["file"], arcname=f"{b.name}/{b.manifest['database']['file']}")
        yield sink.take()
        for rel, _ in b.manifest["files"]:
            tar.add(_files_dir() / rel, arcname=f"{b.name}/files/{rel}")
            chunk = sink.take()
            if chunk:
                yield chunk
    yield sink.take()


def archive_size(b: BackupInfo) -> int:
    """Roughly the size of the archive, for the Settings page (tar adds about 1 KB per file)."""
    return b.manifest["database"]["size"] + b.manifest.get("media_bytes", 0) + 1024 * (len(b.manifest["files"]) + 3)


# --- restore -------------------------------------------------------------------------------


def _open_source(source: Path) -> tuple[Path, Path, Path | None]:
    """A backup folder, or a downloaded .tar of one: (folder with manifest.json, files folder, temp dir to clean up)."""
    if source.is_dir():
        files = source / "files" if (source / "files").is_dir() else source.parent / "files"
        return source, files, None
    if source.is_file() and tarfile.is_tarfile(source):
        tmp = Path(tempfile.mkdtemp(prefix="coinvault-restore-"))
        with tarfile.open(source) as tar:
            tar.extractall(tmp, filter="data")
        dirs = [d for d in tmp.iterdir() if (d / "manifest.json").exists()]
        if len(dirs) != 1:
            shutil.rmtree(tmp, ignore_errors=True)
            raise BackupError("That archive doesn't hold exactly one Coin Vault backup")
        return dirs[0], dirs[0] / "files", tmp
    raise BackupError(f"{source} is neither a backup folder nor a backup archive")


def restore(source: Path, database_url: str, media_root: Path) -> dict:
    """Put a backup back: the database is replaced, missing media files are copied in. Stop the app first.

    Returns the backup's manifest. Afterwards run the migrations (the app does on start) in case the backup
    came from an older version.
    """
    folder, files_dir, tmp = _open_source(Path(source))
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest.get("format") != FORMAT:
            raise BackupError("This backup was made by a newer Coin Vault; update the app first")
        db_file = folder / manifest["database"]["file"]
        if _sha256(db_file) != manifest["database"]["sha256"]:
            raise BackupError("The database file in this backup is damaged (its checksum doesn't match)")
        missing = [rel for rel, size in manifest["files"] if not (files_dir / rel).exists() or (files_dir / rel).stat().st_size != size]
        if missing:
            raise BackupError(f"{len(missing)} files of this backup are missing, for example {missing[0]}")
        kind = manifest["database"]["kind"]
        if kind == "postgresql":
            if not database_url.startswith("postgresql"):
                raise BackupError("This is a PostgreSQL backup; the app is set up for SQLite")
            _restore_postgres(db_file, database_url)
        else:
            if not database_url.startswith("sqlite"):
                raise BackupError("This is a SQLite backup; the app is set up for PostgreSQL")
            target = _sqlite_path(database_url)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_db = target.with_name(f".tmp-restore-{target.name}")
            shutil.copy2(db_file, tmp_db)
            for extra in (target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
                extra.unlink(missing_ok=True)
            os.replace(tmp_db, target)
        media_root.mkdir(parents=True, exist_ok=True)
        for rel, _ in manifest["files"]:
            dest = media_root / rel
            if dest.exists() and dest.stat().st_size == (files_dir / rel).stat().st_size:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmpf = dest.with_name(f".tmp-{dest.name}")
            shutil.copy2(files_dir / rel, tmpf)
            os.chmod(tmpf, 0o640)
            os.replace(tmpf, dest)
        return manifest
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def _restore_postgres(dump: Path, url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            # everything the app owns lives in the public schema: start it empty
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()
    args, env = _pg_env(url)
    r = subprocess.run([_tool("pg_restore"), "--no-owner", "--no-privileges", "--single-transaction", "--exit-on-error", *args, str(dump)],
                       env=env, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise BackupError(f"pg_restore failed: {r.stderr.strip()[:400]}")
