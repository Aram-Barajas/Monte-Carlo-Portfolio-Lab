"""Bounded request admission and security headers for the public API."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import logging
from math import ceil
import os
from threading import Lock
from time import monotonic
from uuid import uuid4

from starlette.responses import JSONResponse


logger = logging.getLogger("uvicorn.error")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


@dataclass(frozen=True)
class HttpLimits:
    max_body_bytes: int = 65536
    requests_per_window: int = 120
    window_seconds: int = 60
    max_concurrent: int = 2
    max_clients: int = 4096
    body_timeout_seconds: int = 10

    def __post_init__(self):
        for name, value in vars(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")

    @classmethod
    def from_env(cls):
        settings = {
            "max_body_bytes": "PORTFOLIO_MAX_BODY_BYTES",
            "requests_per_window": "PORTFOLIO_RATE_LIMIT",
            "window_seconds": "PORTFOLIO_RATE_WINDOW_SECONDS",
            "max_concurrent": "PORTFOLIO_MAX_CONCURRENT",
            "max_clients": "PORTFOLIO_MAX_RATE_CLIENTS",
            "body_timeout_seconds": "PORTFOLIO_BODY_TIMEOUT_SECONDS",
        }
        values = {}
        for field, variable in settings.items():
            if variable in os.environ:
                try:
                    values[field] = int(os.environ[variable])
                    if values[field] < 1:
                        raise ValueError
                except ValueError:
                    raise ValueError(f"{variable} must be a positive integer.") from None
        return cls(**values)


class RequestGate:
    """Bounded per-client fixed windows and a process-wide in-flight limit."""

    def __init__(self, limits, clock=monotonic):
        self.limits = limits
        self.clock = clock
        self.clients = OrderedDict()
        self.active = 0
        self.lock = Lock()

    def admit(self, client):
        """Return (rejection status, retry-after), or (None, None) with a slot."""
        with self.lock:
            now = self.clock()
            expires, count = self.clients.get(client, (now + self.limits.window_seconds, 0))
            if now >= expires:
                expires, count = now + self.limits.window_seconds, 0
            if count >= self.limits.requests_per_window:
                return 429, max(1, ceil(expires - now))
            self.clients[client] = (expires, count + 1)
            self.clients.move_to_end(client)
            while len(self.clients) > self.limits.max_clients:
                self.clients.popitem(last=False)
            if self.active >= self.limits.max_concurrent:
                return 503, 2
            self.active += 1
            return None, None

    def release(self):
        with self.lock:
            self.active -= 1


class BodyTooLarge(Exception):
    pass


async def read_bounded_body(receive, limit):
    chunks = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        body = message.get("body", b"")
        if len(chunks) + len(body) > limit:
            raise BodyTooLarge
        chunks.extend(body)
        if not message.get("more_body", False):
            return bytes(chunks)


class HttpSecurityMiddleware:
    """ASGI middleware: check actual body size and reject excess work before parsing."""

    def __init__(self, app, limits=None):
        self.app = app
        self.limits = limits or HttpLimits.from_env()
        self.gate = RequestGate(self.limits)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        is_api = path.startswith("/api/")
        guarded = is_api and scope.get("method") == "POST"
        request_id = uuid4().hex
        started = monotonic()
        response_started = False
        status_code = None
        acquired = False

        async def guarded_send(message):
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = {
                    b"x-request-id": request_id.encode("ascii"),
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                # Swagger/ReDoc use third-party assets and inline bootstrap
                # code; preserve local interactive API documentation.
                if path not in ("/docs", "/docs/oauth2-redirect", "/redoc"):
                    headers[b"content-security-policy"] = CSP.encode("ascii")
                if is_api:
                    headers[b"cache-control"] = b"no-store"
                message = {**message, "headers": [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() not in headers
                ] + list(headers.items())}
            await send(message)

        async def reject(code, detail, retry=None):
            headers = {"Retry-After": str(retry)} if retry is not None else None
            response = JSONResponse({"detail": detail}, status_code=code, headers=headers)
            await response(scope, receive, guarded_send)

        try:
            if guarded:
                headers = dict(scope.get("headers", []))
                content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                if content_type != b"application/json":
                    await reject(415, "Requests must use application/json.")
                    return
                raw_length = headers.get(b"content-length")
                if raw_length is not None:
                    if not raw_length.isdigit():
                        await reject(400, "Invalid Content-Length.")
                        return
                    try:
                        length = int(raw_length)
                    except ValueError:
                        await reject(400, "Invalid Content-Length.")
                        return
                    if length > self.limits.max_body_bytes:
                        await reject(413, "Request body is too large.")
                        return
                # Only trust the ASGI peer, never raw X-Forwarded-For input.
                client = scope.get("client")
                rejection, retry = self.gate.admit(client[0] if client else "unknown")
                if rejection:
                    detail = "Too many requests. Try again later." if rejection == 429 else "Server is busy. Try again shortly."
                    await reject(rejection, detail, retry)
                    return
                acquired = True
                try:
                    body = await asyncio.wait_for(
                        read_bounded_body(receive, self.limits.max_body_bytes),
                        timeout=self.limits.body_timeout_seconds,
                    )
                except BodyTooLarge:
                    await reject(413, "Request body is too large.")
                    return
                except asyncio.TimeoutError:
                    await reject(408, "Request body timed out.")
                    return
                if body is None:
                    return
                replayed = False

                async def replay_receive():
                    nonlocal replayed
                    if not replayed:
                        replayed = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()

                await self.app(scope, replay_receive, guarded_send)
            else:
                await self.app(scope, receive, guarded_send)
        except Exception:
            # Never expose stack traces or internal exception messages to clients.
            logger.exception("Unhandled request error request_id=%s", request_id)
            if response_started:
                raise
            await reject(500, "An internal server error occurred.")
        finally:
            if acquired:
                self.gate.release()
            if is_api:
                route = getattr(scope.get("route"), "path", "<unmatched>")
                logger.info("api request_id=%s method=%s route=%s status=%s duration_ms=%.1f",
                            request_id, scope.get("method"), route, status_code, (monotonic() - started) * 1000)
