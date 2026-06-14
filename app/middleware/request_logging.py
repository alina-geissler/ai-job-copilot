"""HTTP request/response logging middleware.

Assigns a short unique request ID to every inbound request, logs method,
path, status code, and duration on completion, and forwards the ID as the
``X-Request-ID`` response header for client-side correlation.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_SKIP_PATHS = frozenset({"/health", "/favicon.ico"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with a correlation ID, method, path, status, and duration.

    Stores the generated ``request_id`` on ``request.state`` so route handlers
    can include it in their own log records via ``request.state.request_id``.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process one request: attach ID, delegate, log result.

        :param request: Incoming HTTP request.
        :param call_next: Next middleware or route handler.
        :return: HTTP response with ``X-Request-ID`` header attached.
        """
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        path = request.url.path
        if path not in _SKIP_PATHS:
            logger.info(
                "http.request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

        response.headers["X-Request-ID"] = request_id
        return response
