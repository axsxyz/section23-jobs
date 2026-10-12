from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_aggregator.db.engine import async_session
from job_aggregator.db.models import JobFamily, JobFamilyKeyword, User
from job_aggregator.webapp.auth import require_admin, require_auth_api
from job_aggregator.webapp.schemas import (
    FamilyCreate,
    FamilyOut,
    FamilyUpdate,
    KeywordCreate,
    KeywordOut,
)

router = APIRouter(prefix="/api/families", tags=["families"])


async def _get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session


@router.get("", response_model=list[FamilyOut], dependencies=[Depends(require_auth_api)])
async def list_families(session: AsyncSession = Depends(_get_session)):
    stmt = select(JobFamily).order_by(JobFamily.sort_order, JobFamily.display_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
async def create_family(
    body: FamilyCreate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    family = JobFamily(
        slug=body.slug,
        display_name=body.display_name,
        description=body.description,
        sort_order=body.sort_order,
    )
    session.add(family)
    await session.commit()
    await session.refresh(family)
    return family


@router.put("/{family_id}", response_model=FamilyOut)
async def update_family(
    family_id: uuid.UUID,
    body: FamilyUpdate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(JobFamily).where(JobFamily.id == family_id)
    result = await session.execute(stmt)
    family = result.scalar_one_or_none()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    if body.display_name is not None:
        family.display_name = body.display_name
    if body.description is not None:
        family.description = body.description
    if body.sort_order is not None:
        family.sort_order = body.sort_order
    await session.commit()
    await session.refresh(family)
    return family


@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family(
    family_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(JobFamily).where(JobFamily.id == family_id)
    result = await session.execute(stmt)
    family = result.scalar_one_or_none()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    await session.delete(family)
    await session.commit()


@router.post("/{family_id}/keywords", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
async def add_keyword(
    family_id: uuid.UUID,
    body: KeywordCreate,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(JobFamily).where(JobFamily.id == family_id)
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Family not found")
    kw = JobFamilyKeyword(family_id=family_id, keyword=body.keyword.strip())
    session.add(kw)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Keyword already exists for this family")
    await session.refresh(kw)
    return kw


@router.delete("/{family_id}/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(
    family_id: uuid.UUID,
    keyword_id: uuid.UUID,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(_get_session),
):
    stmt = select(JobFamilyKeyword).where(
        JobFamilyKeyword.id == keyword_id,
        JobFamilyKeyword.family_id == family_id,
    )
    result = await session.execute(stmt)
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    await session.delete(kw)
    await session.commit()
