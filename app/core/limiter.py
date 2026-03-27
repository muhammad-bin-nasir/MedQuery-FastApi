from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_token


def get_user_key(request: Request) -> str:
    """Rate-limit key for authenticated endpoints: JWT subject (user UUID) when present, IP otherwise."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = decode_token(token)
            return f"user:{payload.sub}"
        except Exception:
            pass
    return get_remote_address(request)


# Shared limiter singleton — default key is client IP (used for unauthenticated endpoints).
limiter = Limiter(key_func=get_remote_address)
