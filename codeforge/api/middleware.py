"""Structured request logging middleware.

Logs ONLY permitted metadata: request id, method, endpoint, status code and
duration. Request/response bodies, tokens, prompts and credentials are never
logged. User id / role / redaction metadata are logged by the service layer,
which has the verified context.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("codeforge.api.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration = round(time.monotonic() - started, 3)
            logger.error(
                "request_id=%s method=%s path=%s status=500 duration=%.3f error_category=unhandled",
                request_id,
                request.method,
                request.url.path,
                duration,
            )
            raise
        duration = round(time.monotonic() - started, 3)
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration=%.3f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        response.headers["X-Request-ID"] = request_id
        return response
