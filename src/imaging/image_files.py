# Decode generated images, save assets and combine recap pages.

import base64
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

from src.core.paths import OUTPUT_DIR

logger = logging.getLogger(__name__)


def decode_image(response_data: dict[str, Any]) -> bytes:
    """Validate the API response and decode its first image."""
    data = response_data.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("API response does not contain data")
    item = data[0]
    if isinstance(item, dict):
        image_base64 = item.get("b64_json")
    elif isinstance(item, str):
        image_base64 = item
    else:
        raise ValueError("Invalid data[0] in response")
    if not isinstance(image_base64, str) or not image_base64:
        raise ValueError("Missing data[0].b64_json in response")

    if image_base64.startswith("data:"):
        _, separator, image_base64 = image_base64.partition(",")
        if not separator:
            raise ValueError("Invalid image data URI")

    return base64.b64decode(image_base64, validate=True)


def image_extension(image_bytes: bytes) -> str:
    """Identify an image format from its file signature."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if (
        image_bytes.startswith(b"RIFF")
        and image_bytes[8:12] == b"WEBP"
    ):
        return ".webp"
    raise ValueError("Unsupported image format")


def save_image(
    response_data: dict[str, Any],
    output_name: str = "shopping_recap",
    *,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    image_bytes = decode_image(response_data)
    extension = image_extension(image_bytes)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{output_name}{extension}"
    output_path.write_bytes(image_bytes)
    logger.info("Image saved: %s", output_path)
    return output_path


def save_images(
    response_data: dict[str, Any],
    output_name: str = "shopping_recap",
    *,
    output_dir: Path = OUTPUT_DIR,
) -> list[Path]:
    """Save every base64 image in data, using a unique batch identifier."""
    data = response_data.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("API response does not contain data")

    batch_id = uuid4().hex
    return [
        save_image(
            {"data": [item]},
            output_name=f"{output_name}_{batch_id}_{index:03d}",
            output_dir=output_dir,
        )
        for index, item in enumerate(data, start=1)
    ]


def stack_recap_pages(paths: list[Path], output: Path) -> Path:
    """Return every rendered page in one PNG, preserving their dimensions."""
    pages = []
    for path in paths:
        with Image.open(path) as source:
            pages.append(source.convert("RGB"))
    width = max(page.width for page in pages)
    image = Image.new("RGB", (width, sum(page.height for page in pages)))
    top = 0
    for page in pages:
        image.paste(page, ((width - page.width) // 2, top))
        top += page.height
    image.save(output, format="PNG")
    return output
