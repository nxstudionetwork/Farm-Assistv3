import time
import hashlib
from typing import Dict, Tuple, Callable
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(self), camera=(self)"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        key = hashlib.md5(f"{client_ip}:{request.url.path}".encode()).hexdigest()
        now = time.time()
        window_start = now - self.window_seconds

        if key in self.requests:
            self.requests[key] = [t for t in self.requests[key] if t > window_start]
            if len(self.requests[key]) >= self.max_requests:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "success": False,
                        "detail": f"Too many requests. Try again in {self.window_seconds} seconds.",
                    },
                )
            self.requests[key].append(now)
        else:
            self.requests[key] = [now]

        return await call_next(request)
