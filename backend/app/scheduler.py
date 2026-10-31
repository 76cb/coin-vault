"""Background jobs inside the API process (APScheduler, no Redis/Celery).

Only one process runs the jobs: on PostgreSQL it holds an advisory lock for its lifetime,
so a second uvicorn worker (or a second container) stays quiet.
"""

from __future__ import annotations

import datetime as dt

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.db import get_engine, session_factory
from app.logging_setup import log

LOCK_ID = 827463184
_scheduler: BackgroundScheduler | None = None
_lock_conn = None


def _acquire_lock() -> bool:
    global _lock_conn
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return True
    _lock_conn = engine.connect()
    got = _lock_conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({LOCK_ID})").scalar()
    if not got:
        _lock_conn.close()
        _lock_conn = None
    return bool(got)


def job_poll_spot() -> None:
    from app.services import spot

    with session_factory()() as db:
        try:
            for outcome in spot.poll(db):
                if outcome.ok:
                    log.info("spot_poll", currency=outcome.currency, source=outcome.source)
                elif outcome.skipped_reason:
                    log.info("spot_poll_skipped", currency=outcome.currency, reason=outcome.skipped_reason)
        except Exception:  # never let a job crash the scheduler
            log.exception("spot_poll_crashed")


def job_sync_quotas() -> None:
    from app.services import provider_admin

    with session_factory()() as db:
        try:
            provider_admin.sync_all_usage(db)
        except Exception:
            log.exception("quota_sync_crashed")


def job_backup() -> None:
    from app.services import backup
    from app.services.providers import get_system, set_system

    with session_factory()() as db:
        if not get_system(db, "backup_enabled"):
            return
        try:
            b = backup.run_backup(db, reason="nightly")
            set_system(db, "backup_last", {"at": b.manifest["created_at"], "ok": True, "name": b.name, "error": None})
        except Exception as exc:  # recorded for Settings; never crash the scheduler
            log.exception("backup_failed")
            set_system(db, "backup_last", {"at": dt.datetime.now(dt.UTC).isoformat(), "ok": False, "name": None, "error": str(exc)[:500]})
        db.commit()


def job_value_updates() -> None:
    from app.services import value_updates
    from app.services.providers import get_system

    with session_factory()() as db:
        if not get_system(db, "updates_enabled") or value_updates.is_running(db):
            return
        try:
            value_updates.run_and_record(db)
        except Exception:  # recorded for Settings; never crash the scheduler
            pass


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _updates_trigger(day: str, at: str) -> CronTrigger:
    hour, minute = (int(x) for x in at.split(":"))
    return CronTrigger(day_of_week=day if day in DAYS else "sun", hour=hour, minute=minute)


def _backup_trigger(at: str) -> CronTrigger:
    hour, minute = (int(x) for x in at.split(":"))
    return CronTrigger(hour=hour, minute=minute)


def start() -> None:
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled or _scheduler is not None:
        return
    if not _acquire_lock():
        log.info("scheduler_not_started", reason="another process holds the scheduler lock")
        return
    from app.services.providers import get_system

    with session_factory()() as db:
        minutes = int(get_system(db, "spot_poll_minutes") or 15)
        backup_at = str(get_system(db, "backup_time") or "03:15")
        updates_day = str(get_system(db, "updates_day") or "sun")
        updates_at = str(get_system(db, "updates_time") or "05:40")
    _scheduler = BackgroundScheduler(timezone=s.timezone, job_defaults={"coalesce": True, "max_instances": 1})
    _scheduler.add_job(
        job_poll_spot,
        IntervalTrigger(minutes=minutes),
        id="spot_poll",
        next_run_time=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5),
        misfire_grace_time=300,
    )
    _scheduler.add_job(job_sync_quotas, CronTrigger(hour=4, minute=10), id="quota_sync", misfire_grace_time=3600)
    _scheduler.add_job(job_backup, _backup_trigger(backup_at), id="backup", misfire_grace_time=6 * 3600)
    _scheduler.add_job(job_value_updates, _updates_trigger(updates_day, updates_at), id="value_updates", misfire_grace_time=24 * 3600)
    _scheduler.start()
    log.info("scheduler_started", spot_poll_minutes=minutes)


def reschedule_spot(minutes: int) -> None:
    if _scheduler is not None:
        _scheduler.reschedule_job("spot_poll", trigger=IntervalTrigger(minutes=minutes))
        log.info("spot_poll_rescheduled", minutes=minutes)


def reschedule_backup(at: str) -> None:
    if _scheduler is not None:
        _scheduler.reschedule_job("backup", trigger=_backup_trigger(at))
        log.info("backup_rescheduled", at=at)


def reschedule_updates(day: str, at: str) -> None:
    if _scheduler is not None:
        _scheduler.reschedule_job("value_updates", trigger=_updates_trigger(day, at))
        log.info("value_updates_rescheduled", day=day, at=at)


def next_updates_run() -> dt.datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("value_updates")
    return job.next_run_time if job else None


def next_backup_run() -> dt.datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("backup")
    return job.next_run_time if job else None


def next_spot_run() -> dt.datetime | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("spot_poll")
    return job.next_run_time if job else None


def running() -> bool:
    return _scheduler is not None and _scheduler.running


def stop() -> None:
    global _scheduler, _lock_conn
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _lock_conn is not None:
        _lock_conn.close()
        _lock_conn = None
