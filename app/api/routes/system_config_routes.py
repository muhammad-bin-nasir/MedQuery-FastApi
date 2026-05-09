from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_session
from app.models import BusinessAdmin
from app.services.system_config_service import (
    get_openai_api_key_status,
    set_openai_api_key,
)

router = APIRouter(prefix="/admin/system-config", tags=["System Config"])


class OpenAIApiKeyStatusOut(BaseModel):
    set: bool
    masked_key: str | None


class OpenAIApiKeyUpdate(BaseModel):
    value: str = Field(..., min_length=1, max_length=2000)


@router.get("/openai-api-key", response_model=OpenAIApiKeyStatusOut)
async def get_openai_api_key_status_route(
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> OpenAIApiKeyStatusOut:
    """Return whether the OpenAI API key is configured and show a masked preview."""
    status = await get_openai_api_key_status(session)
    return OpenAIApiKeyStatusOut(set=status["set"], masked_key=status["masked_key"])


@router.put("/openai-api-key")
async def update_openai_api_key(
    payload: OpenAIApiKeyUpdate,
    session: AsyncSession = Depends(get_session),
    admin: BusinessAdmin = Depends(get_current_admin),
) -> dict:
    """Save or replace the OpenAI API key used by chat and embedding features."""
    if not payload.value or not payload.value.strip():
        raise HTTPException(status_code=400, detail="Value cannot be empty")
    try:
        await set_openai_api_key(session, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "OpenAI API key saved."}
