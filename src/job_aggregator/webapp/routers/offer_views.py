from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.engine import async_session
from job_aggregator.db.models import JobOffer, OfferView, User
from job_aggregator.webapp.auth import require_auth_api
from job_aggregator.webapp.schemas import OfferViewCreate, OfferViewOut

router = APIRouter(prefix="/api/views", tags=["offer-views"])


async def _get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


@router.delete("/dismissed", status_code=status.HTTP_204_NO_CONTENT)
async def clear_dismissed(
    current_user: User = Depends(require_auth_api),
    session: AsyncSession = Depends(_get_session),
):
    """Remove all dismissed views for the current user."""
    await session.execute(
        delete(OfferView).where(
            OfferView.user_id == current_user.id,
            OfferView.status == "dismissed",
        )
    )
    await session.commit()


@router.put("/{offer_id}/view", response_model=OfferViewOut)
async def upsert_view(
    offer_id: uuid.UUID,
    body: OfferViewCreate,
    current_user: User = Depends(require_auth_api),
    session: AsyncSession = Depends(_get_session),
):
    """Create or update the current user's status for an offer."""
    offer = await session.get(JobOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(OfferView)
        .values(
            id=uuid.uuid4(),
            user_id=current_user.id,
            offer_id=offer_id,
            status=body.status,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_offer_view_user_offer",
            set_={"status": body.status, "updated_at": now},
        )
        .returning(OfferView.offer_id, OfferView.status, OfferView.updated_at)
    )
    result = await session.execute(stmt)
    await session.commit()
    row = result.fetchone()
    return OfferViewOut(offer_id=row[0], status=row[1], updated_at=row[2])


@router.delete("/{offer_id}/view", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    offer_id: uuid.UUID,
    current_user: User = Depends(require_auth_api),
    session: AsyncSession = Depends(_get_session),
):
    """Remove the current user's status for an offer (fully unsave/unmark)."""
    await session.execute(
        delete(OfferView).where(
            OfferView.user_id == current_user.id,
            OfferView.offer_id == offer_id,
        )
    )
    await session.commit()
