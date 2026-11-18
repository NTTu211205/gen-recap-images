# Generate images through the MWG requests or curl transport.

import logging
from time import perf_counter
from typing import Any

import requests

from src.clients.mwg_http import post_json_with_curl
from src.core.recap_config import RecapConfig

logger = logging.getLogger(__name__)


def build_image_payload(prompt: str, config: RecapConfig) -> dict[str, Any]:
    """Validate the gateway contract once for both HTTP transports."""
    if not 1 <= len(prompt) <= 4000:
        raise ValueError(
            f"Prompt must contain 1-4000 characters; got {len(prompt)}. "
            "Shorten the template or product list before retrying."
        )
    return {
        "model": config.model,
        "translate": config.translate,
        "prompt": prompt,
        "n": 1,
        "size": config.image_size,
        "response_format": "b64_json",
    }


class MWGImageClient:
    """Adapt the MWG HTTP API; the caller owns the session lifecycle."""

    def __init__(
        self, config: RecapConfig, session: requests.Session,
    ) -> None:
        self.config = config
        self.session = session

    def generate_image(self, prompt: str) -> dict[str, Any]:
        payload = build_image_payload(prompt, self.config)
        headers = {
            "apikey": self.config.api_key,
            "Content-Type": "application/json",
        }
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie

        logger.info(
            "Calling MWG API: prompt=%s chars, size=%s, translate=%s",
            len(prompt), self.config.image_size, self.config.translate,
        )
        started = perf_counter()
        with self.session.post(
            self.config.api_url,
            headers=headers,
            json=payload,
            timeout=self.config.timeout,
        ) as response:
            logger.info(
                "HTTP %s received after %.2fs",
                response.status_code, perf_counter() - started,
            )
            if not response.ok:
                logger.error("API failed: HTTP %s", response.status_code)
            response.raise_for_status()
            result = response.json()

        if not isinstance(result, dict):
            raise ValueError("Invalid API response")
        timings = result.get("timings")
        if isinstance(timings, dict):
            for key in ("translate_s", "generate_s"):
                value = timings.get(key)
                if isinstance(value, (int, float)):
                    logger.info("Server %s: %.2fs", key, value)
        logger.info("API request completed in %.2fs", perf_counter() - started)
        return result


class CurlImageClient:
    """Use the same curl transport as the successful standalone request."""

    def __init__(self, config: RecapConfig) -> None:
        self.config = config

    def generate_image(self, prompt: str) -> dict[str, Any]:
        payload = build_image_payload(prompt, self.config)
        logger.info(
            "Calling MWG API via curl: prompt=%s chars, max wait=%ss",
            len(prompt), self.config.timeout[1],
        )
        result = post_json_with_curl(
            self.config.api_url, payload, api_key=self.config.api_key,
            cookie=self.config.cookie, timeout=self.config.timeout,
        )
        timings = result.get("timings")
        if isinstance(timings, dict):
            logger.info("Server timings: %s", {
                key: value for key, value in timings.items()
                if key in ("translate_s", "generate_s")
                and isinstance(value, (int, float))
            })
        return result
