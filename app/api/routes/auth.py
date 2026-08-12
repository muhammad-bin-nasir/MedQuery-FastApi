import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, optional_oauth2_scheme
from app.core.security import create_access_token, decode_token, get_password_hash, verify_password
from app.db.session import get_session
from app.models import Business, BusinessAdmin, Workspace
from app.schemas.auth import (
    CreateAdminRequest,
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UserSignupRequest,
)

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    stmt = select(Business).where(Business.business_client_id == request.business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    stmt = select(BusinessAdmin).where(
        BusinessAdmin.business_id == business.id, BusinessAdmin.email == request.email
    )
    admin = (await session.execute(stmt)).scalar_one_or_none()
    if not admin or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(admin.id), str(business.id), admin.role)
    return TokenResponse(access_token=token)


@router.post("/create-admin")
async def create_admin(
    request: CreateAdminRequest,
    session: AsyncSession = Depends(get_session),
    token: str | None = Depends(optional_oauth2_scheme),
) -> dict:
    caller: BusinessAdmin | None = None
    admins_exist = (
        await session.execute(select(BusinessAdmin.id).limit(1))
    ).scalar_one_or_none() is not None
    if admins_exist:
        if not token:
            raise HTTPException(status_code=403, detail="Super admin required")
        try:
            payload = decode_token(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

        try:
            stmt = select(BusinessAdmin).where(BusinessAdmin.id == uuid.UUID(payload.sub))
            caller = (await session.execute(stmt)).scalar_one_or_none()
        except (ValueError, TypeError):
            caller = None

        if not caller and payload.email:
            rows = list(
                (
                    await session.execute(
                        select(BusinessAdmin).where(BusinessAdmin.email == payload.email)
                    )
                ).scalars().all()
            )
            if rows:
                caller = next((row for row in rows if row.role == "super_admin"), rows[0])

        if not caller or caller.role not in {"super_admin", "admin"}:
            raise HTTPException(status_code=403, detail="Admin required")

    business_client_id = (request.business_client_id or "default").strip() or "default"
    stmt = select(Business).where(Business.business_client_id == business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if caller and caller.role != "super_admin" and caller.business_id != business.id:
        raise HTTPException(status_code=403, detail="Not allowed for this business")

    email = str(request.email).strip().lower()
    stmt = select(BusinessAdmin).where(
        BusinessAdmin.business_id == business.id, BusinessAdmin.email == email
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")

    assigned_role = request.role if request.role in {"admin", "super_admin"} else "admin"
    created = BusinessAdmin(
        id=uuid.uuid4(),
        business_id=business.id,
        email=email,
        password_hash=get_password_hash(request.password),
        role=assigned_role,
    )
    session.add(created)
    await session.commit()
    return {
        "status": "created",
        "user_id": str(created.id),
        "role": created.role,
        "email": created.email,
        "business_client_id": business.business_client_id,
    }


@router.post("/create-user")
async def create_user(
    request: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    stmt = select(Business).where(Business.business_client_id == request.business_client_id)
    business = (await session.execute(stmt)).scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if admin.role != "super_admin" and admin.business_id != business.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    workspace = (
        await session.execute(
            select(Workspace).where(
                Workspace.business_id == business.id,
                Workspace.workspace_id == request.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    email = str(request.email).strip().lower()
    existing = (
        await session.execute(
            select(BusinessAdmin).where(
                BusinessAdmin.business_id == business.id,
                BusinessAdmin.email == email,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.role != "user":
            raise HTTPException(
                status_code=409,
                detail="This email is already used by an admin account.",
            )

        # Adopt an orphaned Project user left by a previous sync attempt.
        existing.password_hash = get_password_hash(request.password)
        await session.commit()
        return {
            "status": "exists",
            "user_id": str(existing.id),
            "email": existing.email,
            "role": existing.role,
        }

    user = BusinessAdmin(
        id=uuid.uuid4(),
        business_id=business.id,
        email=email,
        password_hash=get_password_hash(request.password),
        role="user",
    )
    session.add(user)
    await session.commit()
    return {
        "status": "created",
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
    }


@router.post("/user-signup")
async def user_signup(
    request: UserSignupRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Public signup: registers a role=user account against the default business/workspace."""
    email = request.email.strip().lower()

    business = (
        await session.execute(
            select(Business).where(Business.business_client_id == request.business_client_id)
        )
    ).scalar_one_or_none()
    if not business:
        raise HTTPException(
            status_code=404,
            detail=f"Business '{request.business_client_id}' not found. Create it before signing up users.",
        )

    workspace = (
        await session.execute(
            select(Workspace).where(
                Workspace.business_id == business.id,
                Workspace.workspace_id == request.workspace_id,
            )
        )
    ).scalar_one_or_none()
    if not workspace:
        # Fall back to any workspace in the business so signup is not blocked by naming.
        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.business_id == business.id)
            )
        ).scalars().first()
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail=f"No workspace found for business '{request.business_client_id}'.",
        )

    existing = (
        await session.execute(
            select(BusinessAdmin).where(
                BusinessAdmin.business_id == business.id,
                BusinessAdmin.email == email,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = BusinessAdmin(
        id=uuid.uuid4(),
        business_id=business.id,
        email=email,
        password_hash=get_password_hash(request.password),
        role="user",
    )
    session.add(user)
    await session.commit()

    return {
        "status": "created",
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "business_client_id": business.business_client_id,
        "workspace_id": workspace.workspace_id,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    try:
        target_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    target = (
        await session.execute(select(BusinessAdmin).where(BusinessAdmin.id == target_id))
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.role != "user":
        raise HTTPException(status_code=403, detail="Only role=user can be deleted here")

    if admin.role != "super_admin" and admin.business_id != target.business_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    await session.delete(target)
    await session.commit()
    return {"status": "deleted", "user_id": str(target_id)}
