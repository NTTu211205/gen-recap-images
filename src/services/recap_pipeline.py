# Generate product assets and compose ordered recap pages.

import inspect
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from src.clients.image_generation import CurlImageClient, MWGImageClient
from src.core.concurrency import ordered_parallel_map
from src.imaging.background_templates import (
    GROUPS_PER_PAGE, background_for_groups, require_backgrounds,
)
from src.imaging.image_files import save_images
from src.imaging.product_cutout import (
    merge_product_cutouts, save_product_cutout,
)
from src.imaging.recap_layout import compose_recap, find_font

logger = logging.getLogger(__name__)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _invoke_generate_image(
    client: Any, prompt: str, payload: dict[str, Any],
) -> dict[str, Any]:
    target = getattr(client, "generate_image", client)
    func = getattr(target, "side_effect", None) or target
    try:
        sig = inspect.signature(func)
        accepts_images = (
            "images" in sig.parameters
            or any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
        )
    except (ValueError, TypeError):
        accepts_images = True
    if accepts_images:
        return client.generate_image(
            prompt,
            images=payload.get("images"),
            size=payload.get("size"),
            steps=payload.get("steps"),
            cfg=payload.get("cfg"),
        )
    return client.generate_image(prompt)


def generate_recap(
    client: MWGImageClient | CurlImageClient,
    plan: dict[str, Any], output_dir: Path, *, image_workers: int = 1,
) -> Path:
    """Generate isolated group assets and compose them into a fixed scene."""
    categories = plan.get("categories")
    if categories is None:
        counts = [sum(bool(products) for products in plan["groups"].values())]
    else:
        counts = [
            len(categories[index:index + GROUPS_PER_PAGE])
            for index in range(0, len(categories), GROUPS_PER_PAGE)
        ]
    if not counts:
        raise ValueError("No product groups ready for image generation")
    require_backgrounds(counts)
    find_font()
    run_dir = output_dir / f"recap_{uuid4().hex}"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "plan.json", plan)
    if not plan["requests"]:
        raise ValueError(f"No products ready; inspect {run_dir / 'plan.json'}")
    request_assets = {}
    source_assets = {}
    assets = {}
    request_settings = {
        key: settings
        for category in (categories or [])
        for key, settings in category.get("request_settings", {}).items()
    }
    # requests.Session is caller-owned and is not shared between threads.
    workers = 1 if isinstance(client, MWGImageClient) else image_workers
    started = perf_counter()

    def generate_asset(item: tuple[str, dict]) -> tuple[str, Path, Path]:
        key, payload = item
        request_started = perf_counter()
        logger.info("Generating image request: %s", key)
        response = _invoke_generate_image(client, payload["prompt"], payload)
        paths = save_images(response, output_name=key, output_dir=run_dir)
        source_path = paths[0]
        logger.info(
            "Image request %s saved in %.2fs",
            key, perf_counter() - request_started,
        )
        settings = request_settings.get(key, {})
        cutout_path = save_product_cutout(
            source_path,
            preserve_interior=bool(settings.get("preserve_interior")),
        )
        return key, source_path, cutout_path

    with ordered_parallel_map(
        generate_asset, plan["requests"].items(), workers,
    ) as generated:
        for key, source_path, cutout_path in generated:
            request_assets[key] = cutout_path
            source_assets[key] = source_path
            _write_json(run_dir / "request_assets.json", {
                key: path.name for key, path in request_assets.items()
            })
            if categories is None:
                assets[key] = cutout_path
            else:
                for category in categories:
                    keys = category.get("request_keys", [category["key"]])
                    if (
                        key not in keys
                        or not all(k in request_assets for k in keys)
                    ):
                        continue
                    scales = [
                        float(request_settings.get(k, {}).get("scale", 1.0))
                        for k in keys
                    ]
                    combined = merge_product_cutouts(
                        [request_assets[k] for k in keys],
                        run_dir / f"{category['key']}_group_cutout.png",
                        scales=scales,
                    )
                    assets[category["key"]] = combined
                    category["image_path"] = combined.name
                    category["source_image_paths"] = [
                        source_assets[k].name for k in keys
                    ]
            _write_json(run_dir / "assets.json", {
                group: path.name for group, path in assets.items()
            })
            _write_json(run_dir / "plan.json", plan)
    logger.info("Recap generation/cutouts: %.2fs", perf_counter() - started)
    started = perf_counter()
    result = _compose_pages(assets, plan, run_dir)
    logger.info("Recap composition: %.2fs", perf_counter() - started)
    return result


def _compose_pages(
    assets: dict[str, Path], plan: dict[str, Any], run_dir: Path,
) -> Path:
    """Render all completed groups in plan order and return the first page."""
    categories = plan.get("categories")
    if categories is None:
        return compose_recap(assets, plan["groups"], run_dir / "recap.png")
    outputs = []
    for page_index in range(0, len(categories), GROUPS_PER_PAGE):
        page = categories[page_index:page_index + GROUPS_PER_PAGE]
        names = {}
        for category in page:
            label = category["name"]
            if category["omitted_count"]:
                label += f"\n+{category['omitted_count']} sản phẩm khác"
            names[category["key"]] = label
        output = compose_recap(
            {key: assets[key] for key in names}, plan["groups"],
            run_dir / f"recap_{page_index // GROUPS_PER_PAGE + 1:02d}.png",
            category_names=names,
            category_icons={
                category["key"]: category["id"] for category in page
            },
            category_scales={
                category["key"]: float(category.get("scale", 1.0))
                for category in page
            },
            background_path=background_for_groups(len(page)),
        )
        outputs.append(output)
        logger.info("Recap page saved: %s", output)
    return outputs[0]
