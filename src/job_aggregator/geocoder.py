from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Final

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.config import settings
from job_aggregator.db.models import GeoCache, JobOffer

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_DELAY = 1.1  # seconds between Nominatim requests

# Sentinel that distinguishes "not in cache" from "cached as failed (None, None)"
_CACHE_MISS: Final = object()


def _normalize_location(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.strip().lower()


async def _lookup_nominatim(location: str, client: httpx.AsyncClient) -> tuple[float, float] | None:
    params = {
        "q": location,
        "format": "jsonv2",
        "limit": "1",
        "countrycodes": "fr",
    }
    headers = {"User-Agent": settings.nominatim_user_agent}
    try:
        resp = await client.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        logger.warning("Nominatim lookup failed for %r", location, exc_info=True)
    return None


async def _get_cached(
    session: AsyncSession, key: str
) -> tuple[float, float] | tuple[None, None] | object:
    """Return coords tuple, (None, None) if cached as failed, or _CACHE_MISS if not cached."""
    stmt = select(GeoCache).where(GeoCache.location_key == key)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return _CACHE_MISS
    if row.latitude is not None and row.longitude is not None:
        return row.latitude, row.longitude
    return (None, None)


async def _set_cache(
    session: AsyncSession, key: str, lat: float | None, lon: float | None
) -> None:
    """Insert a cache entry; silently skip if the key already exists."""
    stmt = (
        pg_insert(GeoCache)
        .values(location_key=key, latitude=lat, longitude=lon)
        .on_conflict_do_nothing(index_elements=["location_key"])
    )
    try:
        await session.execute(stmt)
        await session.commit()
    except Exception:
        await session.rollback()


async def _update_offer(
    session: AsyncSession,
    offer_id: int,
    lat: float | None,
    lon: float | None,
) -> None:
    stmt = (
        update(JobOffer)
        .where(JobOffer.id == offer_id)
        .values(latitude=lat, longitude=lon, geocoded_at=datetime.now(timezone.utc))
    )
    try:
        await session.execute(stmt)
        await session.commit()
    except Exception:
        await session.rollback()


async def geocode_missing_offers(session: AsyncSession, batch_size: int = 20) -> int:
    """Geocode offers that have a location string but no coordinates. Returns count updated."""
    # Select only the columns we need so session rollbacks can never expire ORM objects.
    stmt = (
        select(JobOffer.id, JobOffer.location)
        .where(
            JobOffer.latitude.is_(None),
            JobOffer.location.isnot(None),
            JobOffer.geocoded_at.is_(None),
        )
        .order_by(JobOffer.created_at.asc())
        .limit(batch_size)
    )
    result = await session.execute(stmt)
    offer_rows = result.all()  # list of plain Row(id, location) — not ORM objects

    if not offer_rows:
        return 0

    updated = 0
    async with httpx.AsyncClient() as client:
        for offer_id, location in offer_rows:
            key = _normalize_location(location or "")
            if not key:
                await _update_offer(session, offer_id, None, None)
                continue

            cached = await _get_cached(session, key)
            if cached is _CACHE_MISS:
                coords = await _lookup_nominatim(location or "", client)
                lat, lon = coords if coords else (None, None)
                await _set_cache(session, key, lat, lon)
                await asyncio.sleep(REQUEST_DELAY)
            else:
                lat, lon = cached  # type: ignore[misc]  # either (lat,lon) or (None,None)

            await _update_offer(session, offer_id, lat, lon)

            if lat is not None:
                updated += 1

    logger.info("Geocoded %d/%d offers", updated, len(offer_rows))
    return updated
