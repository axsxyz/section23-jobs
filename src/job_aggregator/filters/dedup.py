from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.models import JobOffer
from job_aggregator.db.repository import find_fuzzy_duplicate, insert_if_new
from job_aggregator.sources.base import RawOffer

logger = logging.getLogger(__name__)


async def ingest_offer(session: AsyncSession, raw: RawOffer) -> JobOffer | None:
    """Deduplicate and persist a raw offer. Returns the JobOffer if new, else None."""
    if not raw.url:
        logger.debug("Skipping offer with empty URL: %s", raw.title)
        return None

    fuzzy_dup = await find_fuzzy_duplicate(session, raw.title, raw.company)
    if fuzzy_dup:
        logger.debug(
            "Fuzzy duplicate found: '%s' matches existing '%s'",
            raw.title,
            fuzzy_dup.title,
        )
        return None

    offer = JobOffer(
        url=raw.url,
        title=raw.title,
        company=raw.company,
        location=raw.location,
        department=raw.department,
        contract_type=raw.contract_type,
        description=raw.description,
        source=raw.source,
        raw_json=raw.raw_json,
        latitude=raw.latitude,
        longitude=raw.longitude,
        expires_at=raw.expires_at,
    )

    inserted = await insert_if_new(session, offer)
    if not inserted:
        logger.debug("URL-hash duplicate: %s", raw.url)
        return None

    logger.info("New offer ingested: [%s] %s @ %s", raw.source, raw.title, raw.company)
    return offer
