from __future__ import annotations

import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.app.core.config import get_settings


logger = logging.getLogger("auto_initiativ.issues")
router = APIRouter(tags=["monitoring"])
_write_lock = threading.Lock()


class ClientIssue(BaseModel):
    kind: Literal["javascript_error", "unhandled_rejection", "api_error"]
    message: str = Field(min_length=1, max_length=2000)
    source: str | None = Field(default=None, max_length=500)
    stack: str | None = Field(default=None, max_length=6000)
    status: int | None = Field(default=None, ge=400, le=599)
    url: str | None = Field(default=None, max_length=1000)


def record_issue(
    kind: str,
    message: str,
    *,
    source: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind[:80],
        "message": message[:2000],
        "source": source[:500] if source else None,
        "details": details or {},
    }
    path = settings.issue_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    logger.error("[%s] %s%s", entry["kind"], entry["message"], f" ({source})" if source else "")


class IssueCaptureMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:
            record_issue(
                "backend_exception",
                str(exc) or type(exc).__name__,
                source=f"{request.method} {request.url.path}",
                details={
                    "exception_type": type(exc).__name__,
                    "traceback": traceback.format_exc(limit=12)[-6000:],
                },
            )
            raise
        if response.status_code >= 500 and request.url.path != "/monitoring/client-errors":
            record_issue(
                "backend_http_error",
                f"HTTP {response.status_code}",
                source=f"{request.method} {request.url.path}",
                details={"status": response.status_code},
            )
        return response


@router.post("/monitoring/client-errors", status_code=status.HTTP_202_ACCEPTED)
def report_client_issue(payload: ClientIssue) -> dict[str, bool]:
    record_issue(
        f"frontend_{payload.kind}",
        payload.message,
        source=payload.source or payload.url,
        details={"stack": payload.stack, "status": payload.status, "url": payload.url},
    )
    return {"accepted": True}
