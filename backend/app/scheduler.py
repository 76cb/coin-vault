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
    _scheduler = BackgroundScheduler(timezone=s.timezone, job_defaults={"coalesce": True, "max_instances": 1})
    _scheduler.add_job(
        job_poll_spot,
        IntervalTrigger(minutes=minutes),
        id="spot_poll",
        next_run_time=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5),
        misfire_grace_time=300,
    )
    _scheduler.add_job(job_sync_quotas, CronTrigger(hour=4, minute=10), id="quota_sync", misfire_grace_time=3600)
    _scheduler.start()
    log.info("scheduler_started", spot_poll_minutes=minutes)


def reschedule_spot(minutes: int) -> None:
    if _scheduler is not None:
        _scheduler.reschedule_job("spot_poll", trigger=IntervalTrigger(minutes=minutes))
        log.info("spot_poll_rescheduled", minutes=minutes)


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
