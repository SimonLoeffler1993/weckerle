"""Hintergrund-Scheduler, der die Zeitpläne ausführt."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app import actions, config
from app.db import SessionLocal
from app.models import Schedule

log = logging.getLogger("weckerle")

_scheduler: BackgroundScheduler | None = None


def timezone() -> ZoneInfo:
    try:
        return ZoneInfo(config.TIMEZONE)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Berlin")


def make_trigger(schedule: Schedule) -> CronTrigger:
    hour, minute = schedule.time.split(":")
    return CronTrigger(
        day_of_week=",".join(schedule.weekday_list),
        hour=int(hour),
        minute=int(minute),
        timezone=timezone(),
    )


def execute(schedule_id: int) -> None:
    with SessionLocal() as session:
        schedule = session.get(Schedule, schedule_id)
        if schedule is None or not schedule.enabled:
            return
        actions.run(session, schedule.device, schedule.action, "zeitplan")


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(
        timezone=timezone(),
        job_defaults={"coalesce": True, "misfire_grace_time": 300, "max_instances": 1},
    )
    _scheduler.start()
    reload()
    log.info("Scheduler gestartet (Zeitzone %s)", timezone())


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def reload() -> None:
    """Liest alle Zeitpläne neu ein. Wird nach jeder Änderung aufgerufen."""
    if _scheduler is None:
        return
    _scheduler.remove_all_jobs()
    with SessionLocal() as session:
        for s in session.scalars(select(Schedule).where(Schedule.enabled.is_(True))):
            if not s.weekday_list:
                continue
            _scheduler.add_job(execute, make_trigger(s), args=[s.id], id=f"schedule-{s.id}")


def next_run(schedule: Schedule) -> datetime | None:
    if not schedule.enabled or not schedule.weekday_list:
        return None
    if _scheduler is not None:
        job = _scheduler.get_job(f"schedule-{schedule.id}")
        if job is not None:
            return job.next_run_time
    return make_trigger(schedule).get_next_fire_time(None, datetime.now(timezone()))
