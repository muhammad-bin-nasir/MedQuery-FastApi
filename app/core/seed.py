import logging

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.db.session import AsyncSessionLocal
from app.models import Business, Workspace, WorkspaceConfig

logger = logging.getLogger(__name__)

DEFAULT_USER_BUSINESS_CLIENT_ID = "default"
DEFAULT_USER_BUSINESS_NAME = "Default"
DEFAULT_USER_WORKSPACE_ID = "default"
DEFAULT_USER_WORKSPACE_NAME = "Default"




async def ensure_default_user_tenant() -> None:
    """Idempotently create the 'default' business and 'default' workspace used for self-registered users.

    This function never deletes or modifies existing data – it only creates
    the business / workspace / config rows if they are missing.
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                await session.execute(select(Business.id).limit(1))
            except (ProgrammingError, OperationalError) as e:
                error_msg = str(e).lower()
                if "does not exist" in error_msg or "relation" in error_msg:
                    logger.warning("Database tables not found – skipping ensure_default_user_tenant.")
                    return
                raise

            business = (
                await session.execute(
                    select(Business).where(Business.business_client_id == DEFAULT_USER_BUSINESS_CLIENT_ID)
                )
            ).scalar_one_or_none()

            if not business:
                business = Business(
                    business_client_id=DEFAULT_USER_BUSINESS_CLIENT_ID,
                    name=DEFAULT_USER_BUSINESS_NAME,
                )
                session.add(business)
                await session.flush()
                logger.info(f"Created default user business: {DEFAULT_USER_BUSINESS_CLIENT_ID}")

            workspace = (
                await session.execute(
                    select(Workspace).where(
                        Workspace.business_id == business.id,
                        Workspace.workspace_id == DEFAULT_USER_WORKSPACE_ID,
                    )
                )
            ).scalar_one_or_none()

            if not workspace:
                workspace = Workspace(
                    business_id=business.id,
                    business_client_id=business.business_client_id,
                    workspace_id=DEFAULT_USER_WORKSPACE_ID,
                    name=DEFAULT_USER_WORKSPACE_NAME,
                )
                session.add(workspace)
                await session.flush()
                logger.info(f"Created default user workspace: {DEFAULT_USER_WORKSPACE_ID}")

            existing_config = (
                await session.execute(
                    select(WorkspaceConfig).where(WorkspaceConfig.workspace_id == workspace.id)
                )
            ).scalar_one_or_none()

            if not existing_config:
                session.add(WorkspaceConfig(
                    business_id=business.id,
                    business_client_id=business.business_client_id,
                    workspace_id=workspace.id,
                    use_local_embeddings=False,
                ))
                logger.info("Created WorkspaceConfig for default user workspace")

            await session.commit()
    except Exception as e:
        logger.error(f"Error during ensure_default_user_tenant: {type(e).__name__}: {e}", exc_info=True)
