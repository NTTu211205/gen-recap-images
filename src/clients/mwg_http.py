# Send MWG JSON requests through curl with credentials passed over stdin.

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def post_json_with_curl(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    cookie: str | None = None,
    timeout: tuple[float, float] = (15, 120),
) -> dict[str, Any]:
    headers = [f"apikey: {api_key}", "Content-Type: application/json"]
    if cookie:
        headers.append(f"Cookie: {cookie}")
    curl_config = "\n".join(
        "header = " + json.dumps(header, ensure_ascii=False)
        for header in headers
    )
    with tempfile.TemporaryDirectory(prefix="mwg_curl_") as directory:
        payload_path = Path(directory) / "payload.json"
        response_path = Path(directory) / "response.json"
        payload_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
        command = [
            "curl", "--config", "-", "--location", "--fail-with-body",
            "--silent", "--show-error", "--request", "POST",
            "--connect-timeout", str(timeout[0]),
            "--max-time", str(timeout[1]),
            "--data-binary", f"@{payload_path}",
            "--output", str(response_path),
            "--write-out",
            "HTTP %{http_code} | connect=%{time_connect}s | "
            "first_byte=%{time_starttransfer}s | total=%{time_total}s",
            url,
        ]
        try:
            completed = subprocess.run(
                command, input=curl_config, text=True,
                capture_output=True, timeout=sum(timeout) + 5,
            )
        except subprocess.TimeoutExpired:
            raise requests.Timeout("curl process timed out") from None
        logger.info("curl: %s", completed.stdout.strip())
        if completed.returncode == 28:
            raise requests.Timeout("curl request timed out")
        if completed.returncode:
            raise requests.RequestException(
                f"curl failed with exit code {completed.returncode}; "
                "check network, HTTP status and credentials"
            )
        result = json.loads(response_path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Invalid API response")
    return result
