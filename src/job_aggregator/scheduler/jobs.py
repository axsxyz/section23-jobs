from __future__ import annotations

import logging

from job_aggregator.config import settings
from job_aggregator.db.engine import async_session
from job_aggregator.db.repository import get_offers_to_notify, get_unscored_offers, mark_notified, log_notification
from job_aggregator.filters.dedup import ingest_offer
from job_aggregator.filters.keywords import passes_keyword_filters
from job_aggregator.sources.base import BaseSource

logger = logging.getLogger(__name__)

_sources: list[BaseSource] = []


def register_source(source: BaseSource) -> None:
    _sources.append(source)


async def fetch_source(source: BaseSource) -> None:
    """Fetch from a single source, filter, deduplicate, and persist."""
    logger.info("Starting fetch from %s", source.name)
    try:
        raw_offers = await source.fetch()
    except Exception:
        logger.error("Failed to fetch from %s", source.name, exc_info=True)
        return

    new_count = 0
    for raw in raw_offers:
        if not passes_keyword_filters(raw):
            continue
        async with async_session() as session:
            result = await ingest_offer(session, raw)
            if result:
                new_count += 1

    logger.info("Fetch from %s complete: %d new offers ingested", source.name, new_count)


async def fetch_france_travail() -> None:
    for s in _sources:
        if s.name == "france_travail":
            await fetch_source(s)


async def fetch_rss() -> None:
    for s in _sources:
        if s.name == "rss":
            await fetch_source(s)


async def fetch_adzuna() -> None:
    for s in _sources:
        if s.name == "adzuna":
            await fetch_source(s)


async def cleanup_expired_offers() -> None:
    """Delete job offers whose expiry date has passed."""
    from datetime import datetime, timezone

    from sqlalchemy import delete

    from job_aggregator.db.models import JobOffer

    now = datetime.now(timezone.utc)
    async with async_session() as session:
        result = await session.execute(
            delete(JobOffer)
            .where(JobOffer.expires_at.isnot(None), JobOffer.expires_at < now)
            .returning(JobOffer.id)
        )
        deleted = len(result.all())
        await session.commit()
    if deleted:
        logger.info("Cleanup: deleted %d expired offers", deleted)


async def geocode_offers() -> None:
    """Geocode offers that have a location string but no coordinates."""
    from job_aggregator.geocoder import geocode_missing_offers

    async with async_session() as session:
        await geocode_missing_offers(session)


async def score_and_notify() -> None:
    """Score unscored offers, then send notifications for high-scoring ones."""
    if settings.scoring_enabled:
        from job_aggregator.filters.scorer import score_offer

        async with async_session() as session:
            unscored = await get_unscored_offers(session, limit=20)

        for offer in unscored:
            score, reason = await score_offer(offer)
            async with async_session() as session:
                from sqlalchemy import select
                from job_aggregator.db.models import JobOffer

                stmt = select(JobOffer).where(JobOffer.id == offer.id)
                result = await session.execute(stmt)
                db_offer = result.scalar_one_or_none()
                if db_offer:
                    db_offer.relevance_score = score
                    db_offer.relevance_reason = reason
                    await session.commit()

    async with async_session() as session:
        to_notify = await get_offers_to_notify(session, settings.scoring_threshold)

    for offer in to_notify:
        await _send_notifications(offer)
        async with async_session() as session:
            await mark_notified(session, offer.id)


async def _send_notifications(offer: object) -> None:
    from job_aggregator.db.models import JobOffer
    assert isinstance(offer, JobOffer)

    if settings.telegram_enabled:
        try:
            from job_aggregator.notifier.telegram import send_telegram
            await send_telegram(offer)
            async with async_session() as session:
                await log_notification(session, offer.id, "telegram", success=True)
        except Exception as exc:
            logger.error("Telegram notification failed", exc_info=True)
            async with async_session() as session:
                await log_notification(session, offer.id, "telegram", success=False, error=str(exc))

    if settings.discord_enabled:
        try:
            from job_aggregator.notifier.discord import send_discord
            await send_discord(offer)
            async with async_session() as session:
                await log_notification(session, offer.id, "discord", success=True)
        except Exception as exc:
            logger.error("Discord notification failed", exc_info=True)
            async with async_session() as session:
                await log_notification(session, offer.id, "discord", success=False, error=str(exc))
