"""Alembic environment. Uses the app's settings for the database URL."""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers tables)
from app.config import get_settings
from app.db import Base, make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    url = _url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = make_engine(_url())
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # Rebuilding a table (SQLite's only way to change a constraint) drops the old one; with foreign keys on,
        # that would cascade-delete every row pointing at it. Off for the migration (it can't change inside a
        # transaction, so before it starts), checked and back on after.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=sqlite,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
    if sqlite:
        if connection.in_transaction():
            connection.commit()
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        if broken:
            raise RuntimeError(f"The migration left rows pointing at missing rows: {broken[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
