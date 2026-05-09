import logging
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.core.security import get_password_hash, normalize_email
from app.db.session import AsyncSessionLocal
from app.models import Business, BusinessAdmin, ChatHeader, ChatRequest, ChatResponse, Workspace, WorkspaceConfig

logger = logging.getLogger(__name__)

DEFAULT_BUSINESS_CLIENT_ID = "default"
DEFAULT_BUSINESS_NAME = "Default Business"
DEFAULT_ADMIN_EMAIL = "admin@admin.com"
DEFAULT_ADMIN_PASSWORD = "admin@12345"
DEFAULT_WORKSPACE_ID = "main"
DEFAULT_WORKSPACE_NAME = "Main Workspace"


async def seed_initial_admin() -> None:
    """Seed initial admin user. Gracefully handles missing database tables."""
    try:
        normalized_default_admin_email = normalize_email(DEFAULT_ADMIN_EMAIL)
        async with AsyncSessionLocal() as session:
            # Reset the user table to a single default admin account.
            # This seed clears existing BusinessAdmin rows and removes stale business admin references.
            try:
                await session.execute(select(BusinessAdmin.id).limit(1))
            except (ProgrammingError, OperationalError) as e:
                # Database tables don't exist yet - migrations need to be run
                error_msg = str(e).lower()
                if "does not exist" in error_msg or "relation" in error_msg:
                    logger.warning(
                        "Database tables not found. Skipping seed. "
                        "Please run migrations first: 'docker compose exec api alembic upgrade head'"
                    )
                    return
                # Re-raise if it's a different database error
                raise

            # Clear dependent chat data first, then reset the user table and business ownership.
            await session.execute(delete(ChatResponse))
            await session.execute(delete(ChatRequest))
            await session.execute(delete(ChatHeader))
            await session.execute(update(Business).values(admin_id=None))
            await session.execute(delete(BusinessAdmin))

            # Ensure default business exists
            business = (
                await session.execute(
                    select(Business).where(
                        Business.business_client_id == DEFAULT_BUSINESS_CLIENT_ID
                    )
                )
            ).scalar_one_or_none()

            if not business:
                business = Business(
                    business_client_id=DEFAULT_BUSINESS_CLIENT_ID,
                    name=DEFAULT_BUSINESS_NAME,
                )
                session.add(business)
                await session.flush()  # ensures business.id is available

            existing_workspace = (
                await session.execute(select(Workspace).where(Workspace.business_id == business.id))
            ).scalar_one_or_none()
            if not existing_workspace:
                workspace = Workspace(
                    business_id=business.id,
                    business_client_id=business.business_client_id,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    name=DEFAULT_WORKSPACE_NAME,
                )
                session.add(workspace)
                await session.flush()
                session.add(WorkspaceConfig(
                    business_id=business.id, 
                    business_client_id=business.business_client_id,
                    workspace_id=workspace.id,
                    use_local_embeddings=False  # Default to ChatGPT API, can be changed via API
                ))

            admin = BusinessAdmin(
                id=uuid.uuid4(),
                business_id=business.id,
                email=normalized_default_admin_email,
                email_normalized=normalized_default_admin_email,
                password_hash=get_password_hash(DEFAULT_ADMIN_PASSWORD),
                role="admin",
            )
            session.add(admin)
            await session.flush()
            business.admin_id = admin.id
            session.add(business)
            await session.commit()
            logger.info(
                f"Seeded default admin: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD} "
                f"(business: {DEFAULT_BUSINESS_CLIENT_ID}, workspace: {DEFAULT_WORKSPACE_ID})"
            )
    except Exception as e:
        logger.error(f"Error during seed_initial_admin: {type(e).__name__}: {e}", exc_info=True)
        # Don't crash the app if seeding fails - just log the error
        # This allows the app to start even if seeding fails
