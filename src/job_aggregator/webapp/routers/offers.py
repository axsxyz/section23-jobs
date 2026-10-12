from __future__ import annotations

import math
import re
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.engine import async_session
from job_aggregator.db.models import JobFamilyKeyword, JobOffer, OfferView, RegionAnchor, User
from job_aggregator.webapp.auth import require_auth_api
from job_aggregator.webapp.geo import haversine_km
from job_aggregator.webapp.schemas import OfferListResponse, OfferOut

router = APIRouter(prefix="/api/offers", tags=["offers"])


async def _get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


def _kw_regex(kw: str) -> str:
    """PostgreSQL case-insensitive word-boundary regex for a keyword.

    Uses \\m / \\M (POSIX word boundaries) so 'mer' won't match 'messagerie'.
    re.escape handles hyphens and other special chars in multi-word keywords.
    """
    return f"\\m{re.escape(kw)}\\M"


@router.get("", response_model=OfferListResponse)
async def list_offers(
    family_id: uuid.UUID | None = Query(None),
    region_id: uuid.UUID | None = Query(None),
    radius_km: float = Query(50),
    contract_type: str | None = Query(None),
    view_status: str | None = Query(None),  # "saved" | "viewed" | "dismissed"
    hide_dismissed: bool = Query(True),
    q: str | None = Query(None),
    anchor_lat: float | None = Query(None),
    anchor_lon: float | None = Query(None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("-created_at"),
    current_user: User = Depends(require_auth_api),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(JobOffer)
    count_stmt = select(func.count()).select_from(JobOffer)

    # --- Family keyword filter ---
    if family_id is not None:
        kw_stmt = select(JobFamilyKeyword.keyword).where(JobFamilyKeyword.family_id == family_id)
        kw_result = await session.execute(kw_stmt)
        keywords = [row[0] for row in kw_result.all()]

        if keywords:
            # ~* = case-insensitive regex; \m/\M = POSIX word boundaries
            haystack = (
                func.coalesce(JobOffer.title, literal("", type_=String))
                + literal(" ", type_=String)
                + func.coalesce(JobOffer.description, literal("", type_=String))
            )
            conditions = [haystack.op("~*")(_kw_regex(kw)) for kw in keywords]
            kw_filter = or_(*conditions)
            stmt = stmt.where(kw_filter)
            count_stmt = count_stmt.where(kw_filter)

    # --- Region filter ---
    region = None
    if region_id is not None:
        r_stmt = select(RegionAnchor).where(RegionAnchor.id == region_id)
        r_result = await session.execute(r_stmt)
        region = r_result.scalar_one_or_none()

    if region is not None:
        dept_codes = region.department_codes or []
        dept_match = JobOffer.department.in_(dept_codes) if dept_codes else literal(False)

        if anchor_lat is None or anchor_lon is None:
            anchor_lat = region.center_lat
            anchor_lon = region.center_lon

        delta_lat = radius_km / 111.0
        delta_lon = radius_km / (111.0 * max(0.01, abs(math.cos(math.radians(anchor_lat)))))

        coord_match = (
            JobOffer.latitude.isnot(None)
            & JobOffer.longitude.isnot(None)
            & (JobOffer.latitude >= anchor_lat - delta_lat)
            & (JobOffer.latitude <= anchor_lat + delta_lat)
            & (JobOffer.longitude >= anchor_lon - delta_lon)
            & (JobOffer.longitude <= anchor_lon + delta_lon)
        )

        region_filter = or_(dept_match, coord_match)
        stmt = stmt.where(region_filter)
        count_stmt = count_stmt.where(region_filter)

    # --- Contract type filter ---
    if contract_type:
        ct_filter = JobOffer.contract_type == contract_type.upper()
        stmt = stmt.where(ct_filter)
        count_stmt = count_stmt.where(ct_filter)

    # --- User view-status filter (e.g. "saved" = show only saved offers) ---
    if view_status in ("viewed", "saved", "dismissed"):
        status_subq = (
            select(OfferView.offer_id)
            .where(OfferView.user_id == current_user.id, OfferView.status == view_status)
            .scalar_subquery()
        )
        stmt = stmt.where(JobOffer.id.in_(status_subq))
        count_stmt = count_stmt.where(JobOffer.id.in_(status_subq))

    # --- Hide dismissed offers (default: true) ---
    if hide_dismissed and view_status != "dismissed":
        dismissed_subq = (
            select(OfferView.offer_id)
            .where(OfferView.user_id == current_user.id, OfferView.status == "dismissed")
            .scalar_subquery()
        )
        stmt = stmt.where(~JobOffer.id.in_(dismissed_subq))
        count_stmt = count_stmt.where(~JobOffer.id.in_(dismissed_subq))

    # --- Free-text search ---
    if q:
        pattern = f"%{q.lower()}%"
        text_filter = or_(
            func.lower(JobOffer.title).like(pattern),
            func.lower(func.coalesce(JobOffer.description, "")).like(pattern),
        )
        stmt = stmt.where(text_filter)
        count_stmt = count_stmt.where(text_filter)

    # --- Count ---
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # --- Sort ---
    if sort == "distance" and anchor_lat is not None:
        stmt = stmt.order_by(JobOffer.created_at.desc())
    elif sort == "created_at":
        stmt = stmt.order_by(JobOffer.created_at.asc())
    else:
        stmt = stmt.order_by(JobOffer.created_at.desc())

    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    # --- Batch-load the current user's view statuses for this page ---
    offer_ids = [o.id for o in rows]
    view_map: dict[uuid.UUID, str] = {}
    if offer_ids:
        views_result = await session.execute(
            select(OfferView.offer_id, OfferView.status).where(
                OfferView.user_id == current_user.id,
                OfferView.offer_id.in_(offer_ids),
            )
        )
        view_map = {row[0]: row[1] for row in views_result.all()}

    # --- Compute distance + haversine post-filter ---
    items: list[OfferOut] = []
    for offer in rows:
        dist: float | None = None
        if anchor_lat is not None and anchor_lon is not None and offer.latitude and offer.longitude:
            dist = round(haversine_km(anchor_lat, anchor_lon, offer.latitude, offer.longitude), 1)

        if region is not None and dist is not None and dist > radius_km:
            dept_codes = region.department_codes or []
            if offer.department not in dept_codes:
                total = max(0, total - 1)
                continue

        items.append(
            OfferOut(
                id=offer.id,
                title=offer.title,
                company=offer.company,
                location=offer.location,
                department=offer.department,
                contract_type=offer.contract_type,
                url=offer.url,
                source=offer.source,
                relevance_score=offer.relevance_score,
                distance_km=dist,
                user_status=view_map.get(offer.id),
                expires_at=offer.expires_at,
                created_at=offer.created_at,
            )
        )

    if sort == "distance" and anchor_lat is not None:
        items.sort(key=lambda o: (o.distance_km is None, o.distance_km or 0))

    return OfferListResponse(items=items, total=total, limit=limit, offset=offset)
