from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Plan
from app.services.system_config_service import get_active_plan_code

DEFAULT_LIMITS = {"max_businesses": 1, "max_workspaces": 1, "max_rag_documents": 10, "max_users": 5}


async def get_active_plan(session: AsyncSession) -> Plan | None:
    """Return the Plan row for the currently active plan code, or None if unset/unknown."""
    plan_code = await get_active_plan_code(session)
    if not plan_code:
        return None
    stmt = select(Plan).where(Plan.code == plan_code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_active_plan_limits(session: AsyncSession) -> dict:
    """Return the usage limits for the active plan, falling back to conservative defaults."""
    plan = await get_active_plan(session)
    if not plan:
        return dict(DEFAULT_LIMITS)
    return {
        "max_businesses": plan.max_businesses,
        "max_workspaces": plan.max_workspaces,
        "max_rag_documents": plan.max_rag_documents,
        "max_users": plan.max_users,
    }
