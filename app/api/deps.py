import logging
import uuid

from fastapi import Depends, Request
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_session
from app.models import BusinessAdmin

logger = logging.getLogger(__name__)


def _elevate_admin(admin: BusinessAdmin) -> BusinessAdmin:
    return BusinessAdmin(
        id=admin.id,
        business_id=admin.business_id,
        workspace_id=admin.workspace_id,
        email=admin.email,
        email_normalized=admin.email_normalized,
        password_hash=admin.password_hash,
        role="super_admin",
    )


async def _get_fallback_admin(session: AsyncSession) -> BusinessAdmin | None:
    stmt = select(BusinessAdmin).order_by(
        case(
            (BusinessAdmin.role == "super_admin", 0),
            (BusinessAdmin.role == "admin", 1),
            else_=2,
        ),
        BusinessAdmin.created_at.asc(),
    )
    admin = (await session.execute(stmt)).scalars().first()
    return _elevate_admin(admin) if admin else None


async def get_current_admin(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> BusinessAdmin:
    """JWT authorization is disabled. If a token is present it is used opportunistically,
    otherwise the first available admin account is used automatically."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            try:
                payload = decode_token(token)
                stmt = select(BusinessAdmin).where(BusinessAdmin.id == uuid.UUID(payload.sub))
                admin = (await session.execute(stmt)).scalar_one_or_none()
                if admin:
                    logger.info("JWT auth bypass enabled; using token subject without enforcing auth")
                    return _elevate_admin(admin)
            except Exception as exc:
                logger.info("JWT auth bypass ignoring invalid token", extra={"error": str(exc)})

    admin = await _get_fallback_admin(session)
    if not admin:
        raise RuntimeError("No admin user found in database. Seed an admin first.")

    logger.info("JWT auth disabled; using fallback admin account")
    return admin


def require_super_admin(admin: BusinessAdmin = Depends(get_current_admin)) -> BusinessAdmin:
    return admin


def require_admin(admin: BusinessAdmin = Depends(get_current_admin)) -> BusinessAdmin:
    return admin


def ensure_rag_access(
    admin: BusinessAdmin,
    *,
    business_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Authorization is disabled; all business/workspace scopes are allowed."""
    return None
