from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.engine import async_session
from job_aggregator.db.models import RegionAnchor, User
from job_aggregator.webapp.auth import require_admin, require_auth_api
from job_aggregator.webapp.schemas import RegionCreate, RegionOut, RegionUpdate

router = APIRouter(prefix="/api/regions", tags=["regions"])


async def _get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


@router.get("", response_model=list[RegionOut], dependencies=[Depends(require_auth_api)])
async def list_regions(session: AsyncSession = Depends(_get_session)):
    stmt = select(RegionAnchor).order_by(RegionAnchor.display_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=RegionOut, status_code=status.HTTP_201_CREATED)
async def create_region(
    body: RegionCreate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    region = RegionAnchor(
        slug=body.slug,
        display_name=body.display_name,
        center_lat=body.center_lat,
        center_lon=body.center_lon,
        department_codes=body.department_codes,
    )
    session.add(region)
    await session.commit()
    await session.refresh(region)
    return region


@router.put("/{region_id}", response_model=RegionOut)
async def update_region(
    region_id: uuid.UUID,
    body: RegionUpdate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(RegionAnchor).where(RegionAnchor.id == region_id)
    result = await session.execute(stmt)
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    if body.display_name is not None:
        region.display_name = body.display_name
    if body.center_lat is not None:
        region.center_lat = body.center_lat
    if body.center_lon is not None:
        region.center_lon = body.center_lon
    if body.department_codes is not None:
        region.department_codes = body.department_codes
    await session.commit()
    await session.refresh(region)
    return region


@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_region(
    region_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(RegionAnchor).where(RegionAnchor.id == region_id)
    result = await session.execute(stmt)
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    await session.delete(region)
    await session.commit()
