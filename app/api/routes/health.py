from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health() -> dict:
    """Simple readiness endpoint used to confirm the API process is alive."""
    return {"status": "ok"}
