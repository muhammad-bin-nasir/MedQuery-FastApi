import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.limiter import limiter
from app.core.security import create_access_token, get_password_hash, normalize_email, verify_password
from app.db.session import get_session
from app.models import Business, BusinessAdmin, Workspace
from app.schemas.auth import CreateAdminRequest, LoginRequest, TokenResponse
from app.schemas.auth import CreateUserRequest

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    """Authenticate a user or admin and return an access token plus any resolved business/workspace scope."""
    business = None
    normalized_email = normalize_email(payload.email)

    stmt = select(BusinessAdmin).where(BusinessAdmin.email_normalized == normalized_email)
    admin = (await session.execute(stmt)).scalar_one_or_none()
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if admin.role == "admin":
        # Admin login is global; business context is chosen later per request path.
        pass
    elif admin.role == "user":
        if not admin.business_id:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        user_business = (await session.execute(select(Business).where(Business.id == admin.business_id))).scalar_one_or_none()
        if not user_business:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        business = user_business
    elif admin.role == "super_admin":
        # Super admin login is global; business context is chosen later per request path.
        pass
    else:
        raise HTTPException(status_code=403, detail="Not allowed")

    assigned_workspace_id = None
    if admin.role == "user" and admin.workspace_id:
        workspace_stmt = select(Workspace).where(Workspace.id == admin.workspace_id)
        workspace = (await session.execute(workspace_stmt)).scalar_one_or_none()
        assigned_workspace_id = workspace.workspace_id if workspace else None

    token = create_access_token(str(admin.id), str(business.id) if business else None, admin.role)
    return TokenResponse(
        access_token=token,
        business_client_id=business.business_client_id if business else None,
        workspace_id=assigned_workspace_id,
        role=admin.role,
    )


@router.post("/create-admin")
async def create_admin(
    request: CreateAdminRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new admin account with global access to management features."""
    normalized_email = normalize_email(request.email)
    stmt = select(BusinessAdmin).where(BusinessAdmin.email_normalized == normalized_email)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    admin = BusinessAdmin(
        id=uuid.uuid4(),
        business_id=None,
        workspace_id=None,
        email=normalized_email,
        email_normalized=normalized_email,
        password_hash=get_password_hash(request.password),
        role="admin",
    )
    session.add(admin)
    await session.commit()
    return {"status": "created"}


@router.post("/create-user")
async def create_user(
    request: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(require_admin),
) -> dict:
    """Create a workspace-scoped user under a business and assign the user role."""
    normalized_email = normalize_email(request.email)

    # Validate business exists
    stmt = select(Business).where(Business.business_client_id == request.business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if admin.role == "admin" and business.admin_id != admin.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Validate workspace exists for the business
    stmt = select(Workspace).where(
        Workspace.business_id == business.id,
        Workspace.workspace_id == request.workspace_id,
    )
    workspace = (await session.execute(stmt)).scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Prevent duplicates
    stmt = select(BusinessAdmin).where(
        BusinessAdmin.business_id == business.id,
        BusinessAdmin.email_normalized == normalized_email,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    user = BusinessAdmin(
        id=uuid.uuid4(),
        business_id=business.id,
        workspace_id=workspace.id,
        email=normalized_email,
        email_normalized=normalized_email,
        password_hash=get_password_hash(request.password),
        role="user",
    )
    session.add(user)
    await session.commit()
    return {"status": "created"}
