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
    for name in ("create-admin", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("--username", required=True)
        p.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)

    engine = get_engine()
    upgrade_to_head(engine)
    if args.cmd == "migrate":
        print("Database is at the latest migration.")
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


if __name__ == "__main__":
    main()
