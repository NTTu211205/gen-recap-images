# Translate selected product names with the MWG Qwen chat API.

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from src.prompts.products import PRODUCT_TRANSLATION_PROMPT

logger = logging.getLogger(__name__)
QWEN_API_URL = "https://ai.itmwg.vn/ai-mwg/qwen35-9b/v1/chat/completions"


def retain_model_identifiers(source: str, description: str) -> str:
    """Copy missing model identifiers from the actual source name."""
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        name = source
    else:
        name = (
            str(data.get("name") or "") if isinstance(data, dict) else source
        )
    identifiers = re.findall(
        r"\b(?=[A-Za-z0-9_-]*\d)"
        r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\b|\b\d{5,}\b",
        name,
    )
    normalized = re.sub(r"[^a-z0-9]", "", description.casefold())
    missing = [
        token for token in dict.fromkeys(identifiers)
        if re.sub(r"[^a-z0-9]", "", token.casefold()) not in normalized
    ]
    if missing:
        description += " (" + ", ".join(missing) + ")"
    return description


def validate_translation(source: str, description: str) -> None:
    """Reject untranslated color/material terms before image generation."""
    try:
        data = json.loads(source)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    color = str(data.get("color") or "").casefold().strip()
    vietnamese_colors = {
        "kem", "đen", "trắng", "đỏ", "vàng", "hồng", "xanh", "tím", "bạc",
    }
    tokens = set(re.findall(r"[^\W\d_]+", description.casefold()))
    if any(
        word in tokens for word in color.split() if word in vietnamese_colors
    ):
        raise ValueError("Qwen did not translate the supplied product color")
    name = str(data.get("name") or "").casefold()
    if re.search(r"\bgang\b", name) and "gang" in tokens:
        raise ValueError(
            "Qwen did not translate the cast-iron product material"
        )


class QwenProductTranslator:
    """Translate product names, reusing translations within the current run."""

    def __init__(
        self,
        post_json: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        model: str = "MWG",
    ) -> None:
        self.post_json = post_json
        self.model = model
        self.cache: dict[str, str] = {}

    def translate(self, name: str) -> str:
        if not name.strip():
            raise ValueError("Product name is empty")
        if name in self.cache:
            return self.cache[name]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PRODUCT_TRANSLATION_PROMPT},
                {"role": "user", "content": name},
            ],
            "temperature": 0,
            "max_tokens": 1024,
            "stream": False,
        }
        logger.info("Translating selected product name with Qwen")
        result = self.post_json(payload)
        choices = result.get("choices")
        if (
            not isinstance(choices, list) or not choices
            or not isinstance(choices[0], dict)
        ):
            raise ValueError("Qwen response does not contain choices[0]")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise ValueError("Qwen product translation was truncated")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("Qwen response does not contain message")
        description = message.get("content")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Qwen product translation is empty")
        description = description.strip()
        if "\n" in description or len(description) > 1000:
            raise ValueError(
                "Qwen must return one concise English product name"
            )
        validate_translation(name, description)
        description = retain_model_identifiers(name, description)
        if len(description) > 1000:
            raise ValueError("Product translation exceeds 1000 characters")
        self.cache[name] = description
        return description
