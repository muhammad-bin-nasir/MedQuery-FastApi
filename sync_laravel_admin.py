"""Sync Laravel admin into FastAPI using the same UUID Laravel uses in JWT sub."""
import asyncio
import sys
import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models import Business, BusinessAdmin

LARAVEL_ADMIN_EMAIL = "admin@acme.test"
LARAVEL_ADMIN_PASSWORD = "Admin@12345"


async def main(admin_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        business = (
            await session.execute(
                select(Business).where(Business.business_client_id == "default")
            )
        ).scalar_one_or_none()

        if not business:
            business = Business(business_client_id="default", name="Default Business")
            session.add(business)
            await session.flush()

        existing = (
            await session.execute(select(BusinessAdmin).where(BusinessAdmin.id == admin_id))
        ).scalar_one_or_none()

        if existing:
            existing.role = "super_admin"
            existing.email = LARAVEL_ADMIN_EMAIL
            existing.password_hash = get_password_hash(LARAVEL_ADMIN_PASSWORD)
            existing.business_id = business.id
            print(f"Updated FastAPI super_admin: {LARAVEL_ADMIN_EMAIL} ({admin_id})")
        else:
            session.add(
                BusinessAdmin(
                    id=admin_id,
                    business_id=business.id,
                    email=LARAVEL_ADMIN_EMAIL,
                    password_hash=get_password_hash(LARAVEL_ADMIN_PASSWORD),
                    role="super_admin",
                )
            )
            print(f"Created FastAPI super_admin: {LARAVEL_ADMIN_EMAIL} ({admin_id})")

        await session.commit()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sync_laravel_admin.py <laravel-admin-uuid>")
        sys.exit(1)
    asyncio.run(main(uuid.UUID(sys.argv[1])))
