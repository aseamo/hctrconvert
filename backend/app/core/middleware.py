"""
HctrConvert — HTTP Middleware
──────────────────────────────
Adds request correlation IDs, latency timing, and security headers.

SOFTWARE ENGINEERING PRINCIPLE: "Cross-Cutting Concerns via Middleware"
- Keep observability and HTTP hardening out of route handlers
- Every response carries X-Request-ID, X-Process-Time-Ms, and security headers
"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ObservabilityAndSecurityMiddleware(BaseHTTPMiddleware):
    """Attach request ID, timing header, and standard security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
