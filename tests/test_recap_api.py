# Verify the HTTP contract without calling MWG or loading a heavy model.

import asyncio
import tempfile
import unittest
from contextlib import AsyncExitStack
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

import requests
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app import app
from src.services.recap_service import (
    ProductSelectionError, RecapBusyError, RecapService,
)
from src.core.recap_config import RecapConfig


class RecapApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stack = AsyncExitStack()
        self.addAsyncCleanup(stack.aclose)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "final.png"
        Image.new("RGB", (20, 20), "navy").save(self.path)
        self.service = MagicMock(spec=RecapService)
        self.service.generate.return_value = self.path
        self.startup = stack.enter_context(patch(
            "app.RecapService.from_settings", return_value=self.service,
        ))
        await stack.enter_async_context(app.router.lifespan_context(app))
        self.client = await stack.enter_async_context(AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ))

    async def test_png_response_preserves_leading_zeroes(self):
        response = await self.client.post(
            "/api/v1/recap", json=["0164779000163", "0164779000164"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(
            response.headers["content-disposition"],
            'inline; filename="recap_final.png"',
        )
        self.assertEqual(response.content, self.path.read_bytes())
        self.service.generate.assert_called_once_with([
            "0164779000163", "0164779000164",
        ])
        self.startup.assert_called_once()

    async def test_invalid_arrays_are_rejected_before_generation(self):
        for body in (
            [], [123], [None], [True], [""], ["abc"], ["../catalog"],
            ["1" * 33], ["1"] * 51, {"productcodes": ["1"]},
        ):
            with self.subTest(body=body):
                response = await self.client.post("/api/v1/recap", json=body)
                self.assertEqual(response.status_code, 422)
        self.service.generate.assert_not_called()

    async def test_missing_codes_are_reported_instead_of_omitted(self):
        excluded = [{"productcode": "999", "reason": "catalog_not_found"}]
        self.service.generate.side_effect = ProductSelectionError(excluded)
        response = await self.client.post("/api/v1/recap", json=["999"])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["products"], excluded)

    async def test_upstream_and_local_errors_have_safe_failure_responses(self):
        for error, status in (
            (requests.Timeout("secret-key"), 504),
            (requests.RequestException("secret-key"), 502),
            (ValueError("secret-key"), 502),
            (OSError("secret-key"), 500),
            (RecapBusyError("secret-key"), 503),
        ):
            with self.subTest(status=status, error=type(error).__name__):
                self.service.generate.side_effect = error
                response = await self.client.post(
                    "/api/v1/recap", json=["001"],
                )
                self.assertEqual(response.status_code, status)
                self.assertNotIn("secret-key", response.text)
                if status == 503:
                    self.assertEqual(response.headers["retry-after"], "5")

    async def test_health_responds_and_parallel_generation_is_rejected(self):
        started, release = Event(), Event()
        service = RecapService(
            RecapConfig(api_key="test"), catalog={}, category_groups={},
            output_dir=self.path.parent,
        )

        def slow_generation(productcodes):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Test worker was not released")
            return self.path

        app.state.recap_service = service
        with patch.object(service, "_generate", side_effect=slow_generation):
            pending = asyncio.create_task(
                self.client.post("/api/v1/recap", json=["001"]),
            )
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                health = await self.client.get("/api/v1/health")
                self.assertEqual(health.status_code, 200)
                busy = await self.client.post("/api/v1/recap", json=["002"])
                self.assertEqual(busy.status_code, 503)
            finally:
                release.set()
                response = await asyncio.wait_for(pending, timeout=3)
            self.assertEqual(response.status_code, 200)

    async def test_routes_docs_and_openapi_match_the_binary_response(self):
        root = await self.client.get("/")
        self.assertEqual(root.json()["status"], "ok")
        for path in ("/api/v1/health", "/api/docs", "/api/redoc"):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, 200)
        response = await self.client.get("/api/openapi.json")
        schema = response.json()
        operation = schema["paths"]["/api/v1/recap"]["post"]
        body = operation["requestBody"]["content"]["application/json"]
        self.assertEqual(body["schema"]["type"], "array")
        self.assertEqual(body["schema"]["minItems"], 1)
        self.assertEqual(body["schema"]["maxItems"], 50)
        self.assertEqual(
            set(operation["responses"]["200"]["content"]), {"image/png"},
        )
