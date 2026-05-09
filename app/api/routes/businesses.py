from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_session
from app.models import Business, BusinessAdmin
from app.schemas.business import BusinessCreate, BusinessOut

router = APIRouter(prefix="/admin/businesses", tags=["Businesses"])


def _ensure_business_creator(admin: BusinessAdmin) -> None:
    if admin.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin or super admin required")


def _ensure_business_access(admin: BusinessAdmin, business: Business) -> None:
    if admin.role == "super_admin":
        return
    if admin.role == "admin" and business.admin_id == admin.id:
        return
    raise HTTPException(status_code=403, detail="Not allowed")


@router.post("", response_model=BusinessOut)
async def create_business(
    payload: BusinessCreate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> BusinessOut:
    """Create a new business tenant that can own workspaces, users, and documents."""
    _ensure_business_creator(admin)
    owner_admin_id = payload.admin_id or admin.id
    if owner_admin_id != admin.id:
        raise HTTPException(status_code=403, detail="Business admin must match the authenticated creator")

    existing = (
        await session.execute(
            select(Business).where(Business.business_client_id == payload.business_client_id)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Business already exists")

    business = Business(
        business_client_id=payload.business_client_id,
        name=payload.name,
        admin_id=owner_admin_id,
    )
    session.add(business)
    await session.commit()
    await session.refresh(business)
    return business


@router.get("", response_model=list[BusinessOut])
async def list_businesses(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> list[BusinessOut]:
    """List businesses available to the current account or fallback admin context."""
    if admin.role == "admin":
        stmt = select(Business).where(Business.admin_id == admin.id)
        return list((await session.execute(stmt)).scalars().all())
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    stmt = select(Business)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{business_client_id}", response_model=BusinessOut)
async def get_business(
    business_client_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> BusinessOut:
    """Fetch the details of a single business by its public client identifier."""
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    _ensure_business_access(admin, business)
    return business


@router.delete("/{business_client_id}")
async def delete_business(
    business_client_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    """Delete a business and cascade its related workspaces, users, and documents."""
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    _ensure_business_access(admin, business)
    await session.delete(business)
    await session.commit()
    return {"status": "deleted", "cascade": "workspaces_users_documents"}
