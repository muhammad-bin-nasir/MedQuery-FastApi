from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_super_admin
from app.db.session import get_session
from app.models import BusinessAdmin, Plan
from app.schemas.plan import PlanCreate, PlanOut, PlanUpdate

router = APIRouter(prefix="/admin/plans", tags=["Plans"])


def _ensure_super_admin(admin: BusinessAdmin) -> None:
    if admin.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin required")


@router.get("", response_model=list[PlanOut])
async def list_plans(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_super_admin),
) -> list[Plan]:
    """List every subscription package, ordered for display."""
    _ensure_super_admin(admin)
    stmt = select(Plan).order_by(Plan.sort_order.asc(), Plan.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=PlanOut)
async def create_plan(
    payload: PlanCreate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_super_admin),
) -> Plan:
    """Create a new subscription package tier."""
    _ensure_super_admin(admin)

    existing = (
        await session.execute(select(Plan).where(Plan.code == payload.code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A package with this code already exists")

    plan = Plan(**payload.model_dump())
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


@router.put("/{code}", response_model=PlanOut)
async def update_plan(
    code: str,
    payload: PlanUpdate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_super_admin),
) -> Plan:
    """Update a package's price and/or usage limits."""
    _ensure_super_admin(admin)

    plan = (await session.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Package not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(plan, field, value)

    await session.commit()
    await session.refresh(plan)
    return plan


@router.delete("/{code}")
async def delete_plan(
    code: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_super_admin),
) -> dict:
    """Remove a package tier. It can no longer be purchased or activated afterward."""
    _ensure_super_admin(admin)

    plan = (await session.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Package not found")

    await session.delete(plan)
    await session.commit()
    return {"status": "deleted", "code": code}
