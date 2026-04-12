import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import (
    get_watchlist,
    has_running_scheduled_check,
    get_schedule_settings,
)
from services import create_and_run_check, CheckCreationError

logger = logging.getLogger(__name__)

CRON_JOB_PREFIX = "cron-"

_scheduler: AsyncIOScheduler = None


async def run_scheduled_check() -> None:
    """Fire a scheduled check against the saved watchlist.

    Skips if a previous scheduled run is still in progress, or if the
    watchlist is empty. Any validation or quota error is logged, not raised.
    """
    if await has_running_scheduled_check():
        logger.warning("Previous scheduled check still running, skipping this tick.")
        return

    urls = await get_watchlist()
    if not urls:
        logger.warning("Scheduled check skipped: watchlist is empty.")
        return

    try:
        result = await create_and_run_check(urls, source="scheduled")
        logger.info(
            "Scheduled check %d started with %d URLs.",
            result["check_id"],
            result["url_count"],
        )
    except CheckCreationError as e:
        logger.error("Scheduled check failed to start: %s", e)


def init_scheduler() -> None:
    """Create and start the scheduler engine. No jobs are registered yet —
    call reload_schedule() to load them from the DB."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("Scheduler initialized.")


async def reload_schedule() -> None:
    """Replace all cron-* jobs with ones from the current DB settings."""
    if _scheduler is None:
        logger.warning("reload_schedule called before init_scheduler; no-op.")
        return

    for job in list(_scheduler.get_jobs()):
        if job.id.startswith(CRON_JOB_PREFIX):
            _scheduler.remove_job(job.id)

    settings = await get_schedule_settings()
    if not settings["enabled"]:
        logger.info("Scheduler disabled; no jobs scheduled.")
        return

    try:
        tz = ZoneInfo(settings["timezone"])
    except Exception:
        logger.error(
            "Invalid timezone %r in schedule settings; falling back to UTC.",
            settings["timezone"],
        )
        tz = ZoneInfo("UTC")

    scheduled = 0
    for i, time_str in enumerate(settings["times"]):
        try:
            hour_str, minute_str = time_str.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("out of range")
        except (ValueError, AttributeError):
            logger.warning("Skipping invalid time %r in schedule settings.", time_str)
            continue
        _scheduler.add_job(
            run_scheduled_check,
            CronTrigger(hour=hour, minute=minute, timezone=tz),
            id=f"{CRON_JOB_PREFIX}{i}",
            replace_existing=True,
        )
        scheduled += 1

    logger.info(
        "Scheduler reloaded: %d job(s) at %s in %s.",
        scheduled,
        settings["times"],
        settings["timezone"],
    )


def stop_scheduler() -> None:
    """Stop the scheduler without waiting for running jobs."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
