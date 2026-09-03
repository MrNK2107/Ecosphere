"""
Error handling middleware — structured errors, rate limiting, request IDs.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("agora.errors")


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Rate limiter (simple in-memory sliding window)
# ---------------------------------------------------------------------------
class RateLimiter(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "message": "Too many requests", "retry_after": self.window_seconds},
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._requests[client_ip].append(now)
        return await call_next(request)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
def setup_error_handlers(app: FastAPI):
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(422)
    async def validation_error_handler(request: Request, exc: Any):
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": str(exc.detail) if hasattr(exc, "detail") else str(exc),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Any):
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": str(exc.detail) if hasattr(exc, "detail") else "Resource not found",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc: Any):
        logger.exception(f"Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "Internal server error",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception(f"Generic error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": str(exc)[:200],
                "request_id": getattr(request.state, "request_id", None),
            },
        )
