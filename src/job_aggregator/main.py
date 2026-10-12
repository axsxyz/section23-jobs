from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.interval import IntervalTrigger

from job_aggregator.config import settings
from job_aggregator.db.engine import init_db
from job_aggregator.scheduler.jobs import (
    cleanup_expired_offers,
    fetch_adzuna,
    fetch_france_travail,
    fetch_rss,
    geocode_offers,
    register_source,
    score_and_notify,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Initializing database...")
    await init_db()

    if settings.france_travail_enabled:
        from job_aggregator.sources.france_travail import FranceTravailSource
        register_source(FranceTravailSource())
        logger.info("France Travail source enabled")

    if settings.rss_enabled:
        from job_aggregator.sources.rss import RSSSource
        register_source(RSSSource())
        logger.info("RSS source enabled (%d feeds)", len(settings.feed_urls_list))

    if settings.adzuna_enabled:
        from job_aggregator.sources.adzuna import AdzunaSource
        register_source(AdzunaSource())
        logger.info("Adzuna source enabled")

    if not settings.france_travail_enabled and not settings.rss_enabled and not settings.adzuna_enabled:
        logger.warning("No sources enabled. Configure at least one source in .env")

    async with AsyncScheduler() as scheduler:
        if settings.france_travail_enabled:
            await scheduler.add_schedule(
                fetch_france_travail,
                IntervalTrigger(minutes=settings.fetch_france_travail_interval),
                id="fetch_france_travail",
                conflict_policy=ConflictPolicy.replace,
            )

        if settings.rss_enabled:
            await scheduler.add_schedule(
                fetch_rss,
                IntervalTrigger(minutes=settings.fetch_rss_interval),
                id="fetch_rss",
                conflict_policy=ConflictPolicy.replace,
            )

        if settings.adzuna_enabled:
            await scheduler.add_schedule(
                fetch_adzuna,
                IntervalTrigger(minutes=settings.fetch_adzuna_interval),
                id="fetch_adzuna",
                conflict_policy=ConflictPolicy.replace,
            )

        await scheduler.add_schedule(
            score_and_notify,
            IntervalTrigger(minutes=settings.score_and_notify_interval),
            id="score_and_notify",
            conflict_policy=ConflictPolicy.replace,
        )

        await scheduler.add_schedule(
            cleanup_expired_offers,
            IntervalTrigger(hours=24),
            id="cleanup_expired_offers",
            conflict_policy=ConflictPolicy.replace,
        )
        logger.info("Expiry cleanup scheduled (every 24h)")

        if settings.geocoding_enabled:
            await scheduler.add_schedule(
                geocode_offers,
                IntervalTrigger(minutes=settings.geocode_interval),
                id="geocode_offers",
                conflict_policy=ConflictPolicy.replace,
            )
            logger.info("Geocoder enabled (every %d min)", settings.geocode_interval)

        logger.info("Scheduler started. Running initial fetch...")

        if settings.france_travail_enabled:
            await scheduler.add_job(fetch_france_travail)
        if settings.rss_enabled:
            await scheduler.add_job(fetch_rss)
        if settings.adzuna_enabled:
            await scheduler.add_job(fetch_adzuna)

        logger.info("Job aggregator running. Press Ctrl+C to stop.")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await scheduler.start_in_background()
        await stop_event.wait()

    logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
