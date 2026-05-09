from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_user_key(request: Request) -> str:
    """Rate-limit requests by client address only. JWT-based authorization is disabled."""
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded_for or get_remote_address(request)


# Shared limiter singleton — default key is client IP (used for unauthenticated endpoints).
limiter = Limiter(key_func=get_remote_address)
