import logging
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, delete, select
from sqlalchemy.exc import NoSuchTableError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import normalize_email
from app.db.session import AsyncSessionLocal
from app.models import Business, BusinessAdmin, Workspace

logger = logging.getLogger(__name__)


def get_laravel_engine():
    settings = get_settings()
    if not settings.laravel_database_url:
        return None

    try:
        return create_engine(settings.laravel_database_url, future=True)
    except Exception as exc:
        logger.warning("Unable to create Laravel DB engine: %s", exc)
        return None


def fetch_laravel_users() -> list[dict[str, Any]]:
    engine = get_laravel_engine()
    if engine is None:
        return []

    metadata = MetaData()
    try:
        users_table = Table("users", metadata, autoload_with=engine)
    except NoSuchTableError:
        logger.warning("Laravel users table not found for sync")
        return []
    except OperationalError as exc:
        logger.warning("Unable to connect to Laravel DB for user sync: %s", exc)
        return []

    with engine.connect() as conn:
        result = conn.execute(select(users_table))
        return [dict(row._mapping) for row in result.mappings().all()]


async def sync_users_from_laravel() -> bool:
    rows = fetch_laravel_users()
    if not rows:
        logger.info("No Laravel users were found to sync")
        return False

    normalized_emails: set[str] = set()
    async with AsyncSessionLocal() as session:
        business_ids = {str(id_) for id_, in (await session.execute(select(Business.id))).all()}
        workspace_ids = {str(id_) for id_, in (await session.execute(select(Workspace.id))).all()}

        for row in rows:
            raw_email_normalized = row.get("email_normalized") or row.get("email")
            if raw_email_normalized is None:
                continue

            email_normalized = normalize_email(str(raw_email_normalized))
            if email_normalized == "":
                continue

            normalized_emails.add(email_normalized)
            email = row.get("email") or email_normalized
            password_hash = row.get("password_hash") or ""
            role = row.get("role") or "admin"
            business_id = row.get("business_id")
            workspace_id = row.get("workspace_id")

            if business_id is not None and business_id not in business_ids:
                business_id = None
            if workspace_id is not None and workspace_id not in workspace_ids:
                workspace_id = None

            existing_admin = (
                (await session.execute(
                    select(BusinessAdmin).where(BusinessAdmin.email_normalized == email_normalized)
                )).scalar_one_or_none()
            )

            if existing_admin is None:
                session.add(
                    BusinessAdmin(
                        id=row.get("id"),
                        business_id=business_id,
                        workspace_id=workspace_id,
                        email=email,
                        email_normalized=email_normalized,
                        password_hash=password_hash,
                        role=role,
                    )
                )
            else:
                existing_admin.email = email
                existing_admin.password_hash = password_hash
                existing_admin.role = role
                existing_admin.business_id = business_id
                existing_admin.workspace_id = workspace_id
                session.add(existing_admin)

        if normalized_emails:
            await session.execute(
                delete(BusinessAdmin).where(BusinessAdmin.email_normalized.not_in(normalized_emails))
            )
        await session.commit()

    logger.info("Synced %d Laravel users into Project", len(normalized_emails))
    return bool(normalized_emails)
