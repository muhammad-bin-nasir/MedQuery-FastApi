"""Forward application errors to Laravel Site Logs (best-effort, non-blocking)."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional
from urllib import error, request
import json

logger = logging.getLogger(__name__)


def _laravel_site_logs_url() -> str:
    configured = (
        os.environ.get("LARAVEL_SITE_LOGS_URL")
        or os.environ.get("LARAVEL_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if configured:
        if configured.endswith("/api/site-logs"):
            return configured
        if configured.endswith("/api"):
            return f"{configured}/site-logs"
        return f"{configured}/api/site-logs"
    return "http://127.0.0.1:8001/api/site-logs"


def report_to_laravel(
    *,
    message: str,
    severity: str = "error",
    source: str = "python",
    category: str = "fastapi",
    exception_class: Optional[str] = None,
    stack_trace: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    status_code: Optional[int] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    request_url: Optional[str] = None,
) -> None:
    """Fire-and-forget POST to Laravel /api/site-logs."""

    def _send() -> None:
        payload = {
            "severity": severity,
            "source": source,
            "category": category,
            "message": (message or "Unknown Python error")[:5000],
            "exception_class": exception_class,
            "stack_trace": (stack_trace or "")[:50000] or None,
            "context": context or None,
            "status_code": status_code,
            "request_method": request_method,
            "request_path": request_path,
            "request_url": request_url,
        }
        body = json.dumps({k: v for k, v in payload.items() if v is not None}).encode("utf-8")
        req = request.Request(
            _laravel_site_logs_url(),
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=3) as resp:
                resp.read()
        except error.URLError as exc:
            logger.debug("site_logs.forward_failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("site_logs.forward_failed: %s", exc)

    try:
        threading.Thread(target=_send, daemon=True).start()
    except Exception as exc:  # noqa: BLE001
        logger.debug("site_logs.thread_failed: %s", exc)
