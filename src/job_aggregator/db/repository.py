from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.models import JobOffer, NotificationLog

logger = logging.getLogger(__name__)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


async def insert_if_new(session: AsyncSession, offer: JobOffer) -> bool:
    """Insert an offer if its url_hash is not already present. Returns True if inserted."""
    offer.url_hash = url_hash(offer.url)

    stmt = (
        pg_insert(JobOffer)
        .values(
            id=offer.id or uuid.uuid4(),
            url_hash=offer.url_hash,
            url=offer.url,
            title=offer.title,
            company=offer.company,
            location=offer.location,
            department=offer.department,
            contract_type=offer.contract_type,
            description=offer.description,
            source=offer.source,
            raw_json=offer.raw_json,
            latitude=offer.latitude,
            longitude=offer.longitude,
        )
        .on_conflict_do_nothing(index_elements=["url_hash"])
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) > 0


async def find_fuzzy_duplicate(
    session: AsyncSession, title: str, company: str | None, window_days: int = 7
) -> JobOffer | None:
    """Check for a fuzzy duplicate in the recent window. Done in Python with rapidfuzz."""
    from rapidfuzz import fuzz

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = select(JobOffer).where(JobOffer.created_at >= cutoff)
    result = await session.execute(stmt)
    existing = result.scalars().all()

    candidate = f"{title} {company or ''}".strip().lower()
    for row in existing:
        existing_text = f"{row.title} {row.company or ''}".strip().lower()
        if fuzz.token_sort_ratio(candidate, existing_text) >= 85:
            return row
    return None


async def get_unscored_offers(session: AsyncSession, limit: int = 20) -> list[JobOffer]:
    stmt = (
        select(JobOffer)
        .where(JobOffer.relevance_score.is_(None))
        .order_by(JobOffer.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_offers_to_notify(
    session: AsyncSession, threshold: int = 7
) -> list[JobOffer]:
    stmt = (
        select(JobOffer)
        .where(
            JobOffer.notified.is_(False),
            JobOffer.relevance_score.isnot(None),
            JobOffer.relevance_score >= threshold,
        )
        .order_by(JobOffer.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_notified(session: AsyncSession, offer_id: uuid.UUID) -> None:
    stmt = select(JobOffer).where(JobOffer.id == offer_id)
    result = await session.execute(stmt)
    offer = result.scalar_one_or_none()
    if offer:
        offer.notified = True
        await session.commit()


async def log_notification(
    session: AsyncSession,
    offer_id: uuid.UUID,
    channel: str,
    success: bool = True,
    error: str | None = None,
) -> None:
    entry = NotificationLog(
        offer_id=offer_id, channel=channel, success=success, error=error
    )
    session.add(entry)
    await session.commit()
