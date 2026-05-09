from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemConfig

OPENAI_API_KEY_KEY = "openai_api_key"


def _looks_like_masked_or_placeholder_key(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip()
    if not normalized:
        return True
    placeholders = {"(set)", "(saved)", "saved", "masked", "hidden"}
    if normalized.lower() in placeholders:
        return True
    # Common UI-masked form: prefix...suffix
    if "..." in normalized:
        return True
    return False


async def get_openai_api_key(session: AsyncSession) -> str | None:
    """Return OpenAI API key from DB, or None if not set."""
    stmt = select(SystemConfig).where(SystemConfig.key == OPENAI_API_KEY_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if not row or not (row.value and row.value.strip()):
        return None
    value = row.value.strip()
    # If a masked placeholder was accidentally saved, treat it as unset
    # so we can still fall back to OPENAI_API_KEY from env.
    if _looks_like_masked_or_placeholder_key(value):
        return None
    return value


async def set_openai_api_key(session: AsyncSession, value: str) -> None:
    """Set OpenAI API key in DB. Creates or updates the row."""
    cleaned = value.strip()
    if _looks_like_masked_or_placeholder_key(cleaned):
        raise ValueError("Please paste a full API key value, not a masked placeholder.")

    stmt = select(SystemConfig).where(SystemConfig.key == OPENAI_API_KEY_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        row.value = cleaned
    else:
        session.add(SystemConfig(key=OPENAI_API_KEY_KEY, value=cleaned))
    await session.commit()


async def get_openai_api_key_status(session: AsyncSession) -> dict:
    """Return { set: bool, masked_key: str } for UI (never the full key)."""
    key = await get_openai_api_key(session)
    if not key:
        return {"set": False, "masked_key": None}
    if len(key) <= 11:
        return {"set": True, "masked_key": "(set)"}
    return {"set": True, "masked_key": f"{key[:7]}...{key[-4:]}"}
