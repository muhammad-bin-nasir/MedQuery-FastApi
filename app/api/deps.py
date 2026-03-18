import uuid
import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_session
from app.models import BusinessAdmin

bearer_scheme = HTTPBearer()
optional_bearer_scheme = HTTPBearer(auto_error=False)

# Alias for legacy naming used by auth routes
optional_oauth2_scheme = optional_bearer_scheme

logger = logging.getLogger(__name__)


async def get_current_admin(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> BusinessAdmin:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception as exc:
        logger.warning("Token decode failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    stmt = select(BusinessAdmin).where(BusinessAdmin.id == uuid.UUID(payload.sub))
    result = await session.execute(stmt)
    admin = result.scalar_one_or_none()
    if not admin:
        logger.warning("Admin not found for token", extra={"token_sub": payload.sub})
        raise HTTPException(status_code=401, detail="Admin not found")
    logger.info("Admin authenticated", extra={"admin_id": str(admin.id), "role": admin.role})
    return admin


def require_super_admin(admin: BusinessAdmin = Depends(get_current_admin)) -> BusinessAdmin:
    if admin.role != "super_admin":
        logger.warning("Super admin required but user is not", extra={"admin_id": str(admin.id), "role": admin.role})
        raise HTTPException(status_code=403, detail="Super admin required")
    return admin


def require_admin(admin: BusinessAdmin = Depends(get_current_admin)) -> BusinessAdmin:
    """Allow both admin and super_admin roles."""
    if admin.role not in ("admin", "super_admin"):
        logger.warning(
            "Admin required but user is not", extra={"admin_id": str(admin.id), "role": admin.role}
        )
        raise HTTPException(status_code=403, detail="Admin required")
    return admin


def ensure_rag_access(
    admin: BusinessAdmin,
    *,
    business_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Admins can access any business/workspace; users are limited to their assigned scope."""
    if admin.role in ("admin", "super_admin"):
        return

    if admin.role != "user":
        logger.warning(
            "Unsupported role for RAG access",
            extra={"admin_id": str(admin.id), "role": admin.role},
        )
        raise HTTPException(status_code=403, detail="Not allowed")

    if admin.business_id != business_id or admin.workspace_id != workspace_id:
        logger.warning(
            "User attempted cross-workspace RAG access",
            extra={
                "admin_id": str(admin.id),
                "role": admin.role,
                "requested_business_id": str(business_id),
                "requested_workspace_id": str(workspace_id),
                "assigned_business_id": str(admin.business_id),
                "assigned_workspace_id": str(admin.workspace_id) if admin.workspace_id else None,
            },
        )
        raise HTTPException(status_code=403, detail="Not allowed for this business/workspace")
