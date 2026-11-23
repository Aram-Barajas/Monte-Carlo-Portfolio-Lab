import asyncio
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api import app, FRONTEND_ASSETS
from backend.http_security import HttpLimits, HttpSecurityMiddleware, RequestGate


def make_test_app(limits):
    application = FastAPI()
    application.add_middleware(HttpSecurityMiddleware, limits=limits)

    @application.post("/api/echo")
    async def echo(request: Request):
        return {"body": await request.json()}

    @application.post("/api/fail")
    async def fail():
        raise RuntimeError("PRIVATE EXCEPTION")

    return application


class HttpSecurityTests(unittest.TestCase):
    def test_env_configuration_and_invalid_value(self):
        with patch.dict(os.environ, {"PORTFOLIO_RATE_LIMIT": "17", "PORTFOLIO_MAX_CONCURRENT": "3"}):
            limits = HttpLimits.from_env()
            self.assertEqual(limits.requests_per_window, 17)
            self.assertEqual(limits.max_concurrent, 3)
        for invalid in ("0", "-1", "abc", "1.5"):
            with patch.dict(os.environ, {"PORTFOLIO_RATE_LIMIT": invalid}):
                with self.assertRaisesRegex(ValueError, "PORTFOLIO_RATE_LIMIT"):
                    HttpLimits.from_env()

    def test_headers_and_asset_allowlist(self):
        client = TestClient(app)
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("script-src 'self'", page.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])
        self.assertEqual(page.headers["x-content-type-options"], "nosniff")
        self.assertEqual(page.headers["x-frame-options"], "DENY")
        self.assertEqual(page.headers["referrer-policy"], "no-referrer")
        self.assertEqual(len(page.headers["x-request-id"]), 32)
        health = client.get("/api/health")
        self.assertEqual(health.headers["cache-control"], "no-store")
        self.assertNotEqual(health.headers["x-request-id"], page.headers["x-request-id"])
        for asset in FRONTEND_ASSETS:
            with self.subTest(asset=asset):
                self.assertEqual(client.get("/static/" + asset).status_code, 200)
        for asset in ("index.html", ".env", "backend/api.py", "missing.js", "%2e%2e%2fREADME.md"):
            with self.subTest(asset=asset):
                self.assertEqual(client.get("/static/" + asset).status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 200)

    def test_oversize_and_non_json_body(self):
        client = TestClient(make_test_app(HttpLimits(max_body_bytes=32)))
        self.assertEqual(client.post("/api/echo", json={"x": "a" * 40}).status_code, 413)
        self.assertEqual(client.post("/api/echo", data={"x": 2}).status_code, 415)
        response = client.post("/api/echo", json={"x": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"body": {"x": 1}})
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_rate_limit_rejects_spoofed_forwarded_headers(self):
        client = TestClient(make_test_app(HttpLimits(requests_per_window=2)))
        for ip in ("1.2.3.4", "5.6.7.8"):
            self.assertEqual(client.post("/api/echo", json={}, headers={"X-Forwarded-For": ip}).status_code, 200)
        response = client.post("/api/echo", json={}, headers={"X-Forwarded-For": "9.9.9.9"})
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response.headers["retry-after"]), 1)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_unhandled_error_is_generic_and_releases_slot(self):
        client = TestClient(make_test_app(HttpLimits(max_concurrent=1)))
        with self.assertLogs("uvicorn.error", level="ERROR"):
            response = client.post("/api/fail", json={})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("PRIVATE EXCEPTION", response.text)
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(client.post("/api/echo", json={}).status_code, 200)

    def test_rate_window_concurrency_and_bounded_state(self):
        now = [0.]
        gate = RequestGate(HttpLimits(requests_per_window=2, max_concurrent=1, max_clients=2),
                           clock=lambda: now[0])
        self.assertEqual(gate.admit("a"), (None, None))
        self.assertEqual(gate.admit("b"), (503, 2))
        gate.release()
        self.assertEqual(gate.admit("a"), (None, None))
        gate.release()
        self.assertEqual(gate.admit("a"), (429, 60))
        now[0] = 60
        self.assertEqual(gate.admit("a"), (None, None))
        gate.release()
        self.assertEqual(gate.admit("c"), (None, None))
        gate.release()
        self.assertEqual(len(gate.clients), 2)
        self.assertNotIn("b", gate.clients)
        self.assertEqual(gate.active, 0)


class AsyncHttpSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_streamed_body_actual_size_enforced(self):
        application = make_test_app(HttpLimits(max_body_bytes=16))

        async def chunks():
            yield b'{"x":"'
            yield b'a' * 20
            yield b'"}'

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post("/api/echo", content=chunks(), headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 413)
            self.assertEqual((await client.post("/api/echo", json={})).status_code, 200)

    async def test_concurrency_rejection_and_health_unblocked(self):
        application = FastAPI()
        application.add_middleware(HttpSecurityMiddleware, limits=HttpLimits(max_concurrent=1))
        entered, release = asyncio.Event(), asyncio.Event()

        @application.post("/api/slow")
        async def slow():
            entered.set()
            await release.wait()
            return {"ok": True}

        @application.get("/api/health")
        async def health():
            return {"status": "ok"}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            first = asyncio.create_task(client.post("/api/slow", json={}))
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                busy = await client.post("/api/slow", json={})
                self.assertEqual(busy.status_code, 503)
                self.assertEqual(busy.headers["retry-after"], "2")
                self.assertEqual((await client.get("/api/health")).status_code, 200)
            finally:
                release.set()
                self.assertEqual((await first).status_code, 200)
            self.assertEqual((await client.post("/api/slow", json={})).status_code, 200)

    async def test_slow_body_times_out_and_releases_slot(self):
        application = make_test_app(HttpLimits(body_timeout_seconds=1, max_concurrent=1))
        async def delayed():
            await asyncio.Event().wait()
            yield b"{}"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post("/api/echo", content=delayed(), headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 408)
            self.assertEqual((await client.post("/api/echo", json={})).status_code, 200)
