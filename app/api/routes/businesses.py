from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_session
from app.models import Business, BusinessAdmin
from app.schemas.business import BusinessCreate, BusinessOut, BusinessUpdate

router = APIRouter(prefix="/admin/businesses", tags=["Businesses"])


def _ensure_super_admin(admin: BusinessAdmin) -> None:
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin required")


def _ensure_access(admin: BusinessAdmin, business: Business) -> None:
    if admin.role != "super_admin" and admin.business_id != business.id:
        raise HTTPException(status_code=403, detail="Not allowed")


@router.post("", response_model=BusinessOut)
async def create_business(
    payload: BusinessCreate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> BusinessOut:
    _ensure_super_admin(admin)
    existing = (
        await session.execute(
            select(Business).where(Business.business_client_id == payload.business_client_id)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Business already exists")

    business = Business(business_client_id=payload.business_client_id, name=payload.name)
    session.add(business)
    await session.commit()
    await session.refresh(business)
    return business


@router.get("", response_model=list[BusinessOut])
async def list_businesses(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> list[BusinessOut]:
    if admin.role != "super_admin":
        stmt = select(Business).where(Business.id == admin.business_id)
        return list((await session.execute(stmt)).scalars().all())

    stmt = select(Business)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{business_client_id}", response_model=BusinessOut)
async def get_business(
    business_client_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> BusinessOut:
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    _ensure_access(admin, business)
    return business


@router.put("/{business_client_id}", response_model=BusinessOut)
async def update_business(
    business_client_id: str,
    payload: BusinessUpdate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> BusinessOut:
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if admin.role != "super_admin":
        _ensure_access(admin, business)

    business.name = payload.name.strip()
    await session.commit()
    await session.refresh(business)
    return business


@router.delete("/{business_client_id}")
async def delete_business(
    business_client_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    _ensure_super_admin(admin)
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    await session.delete(business)
    await session.commit()
    return {"status": "deleted", "cascade": "workspaces_admins_documents"}
