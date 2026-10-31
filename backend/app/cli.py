"""Admin commands.

    python -m app.cli migrate
    python -m app.cli create-admin --username admin            # prompts for the password
    echo "$PW" | python -m app.cli create-admin --username admin --password-stdin
    python -m app.cli reset-password --username admin
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import delete, select

from app.db import get_engine, session_factory
from app.migrate import upgrade_to_head
from app.models import User, UserSession
from app.security import MIN_PASSWORD_LENGTH, hash_password


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("New password: ")
        if pw != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match")
    if len(pw) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return pw


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("backup", help="make a backup now (database and media files)")
    sub.add_parser("list-backups", help="list the backups in the backup folder")
    r = sub.add_parser("restore", help="put a backup back (stop the service first)")
    r.add_argument("source", help="a backup's name (from list-backups), its folder, or a downloaded .tar")
    r.add_argument("--yes", action="store_true", help="don't ask before replacing the database")
    for name in ("create-admin", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("--username", required=True)
        p.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd in ("list-backups", "restore"):
        _backups_cli(args)
        return

    engine = get_engine()
    if args.cmd != "backup":  # a backup is taken as the database is (before an update migrates it)
        upgrade_to_head(engine)
    if args.cmd == "migrate":
        print("Database is at the latest migration.")
        return
    if args.cmd == "backup":
        from app.services import backup
        from app.services.providers import set_system

        with session_factory()() as db:
            b = backup.run_backup(db, reason="manual")
            set_system(db, "backup_last", {"at": b.manifest["created_at"], "ok": True, "name": b.name, "error": None})
            db.commit()
        print(f"Backup {b.name}: {b.manifest['counts']['items']} items, {len(b.manifest['files'])} files, in {b.path}")
        return

    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if args.cmd == "create-admin":
            if user is not None:
                sys.exit(f"User {args.username!r} already exists; use reset-password")
            if db.scalar(select(User).where(User.is_admin.is_(True))) is not None:
                print("Note: an admin already exists; creating another admin account.")
            db.add(User(username=args.username, password_hash=hash_password(_read_password(args.password_stdin)), is_admin=True))
            db.commit()
            print(f"Created admin {args.username!r}.")
        else:
            if user is None:
                sys.exit(f"No user {args.username!r}")
            user.password_hash = hash_password(_read_password(args.password_stdin))
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
            db.commit()
            print(f"Password reset for {args.username!r}; all their sessions were signed out.")


def _backups_cli(args) -> None:
    from pathlib import Path

    from app.config import get_settings
    from app.services import backup

    if args.cmd == "list-backups":
        bs = backup.list_backups()
        if not bs:
            print(f"No backups in {backup.backup_root()}")
        for b in bs:
            c = b.manifest["counts"]
            print(f"{b.name}  {b.manifest['reason']:<7}  {c['items']} items, {c['photos']} photos, {len(b.manifest['files'])} files")
        return

    s = get_settings()
    src = Path(args.source)
    if not src.exists():
        src = backup.backup_root() / args.source
    if not args.yes:
        answer = input(f"Replace the database and add missing media files from {src}? Type yes: ")
        if answer.strip().lower() != "yes":
            sys.exit("Nothing changed.")
    try:
        manifest = backup.restore(src, s.database_url, Path(s.media_root).resolve())
    except backup.BackupError as exc:
        sys.exit(f"Restore failed: {exc}")
    upgrade_to_head(get_engine())  # a backup from an older version is brought up to date
    c = manifest["counts"]
    print(f"Restored the backup from {manifest['created_at']}: {c['items']} items, {c['photos']} photos, "
          f"{len(manifest['files'])} files. Start the service again.")


if __name__ == "__main__":
    main()
