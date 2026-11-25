# Resolve product codes from JSON and rank products by catalog metrics.

import hashlib
import json
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.catalog.product_groups import (
    group_products, load_category_groups, product_scale,
)
from src.prompts.products import build_group_edit_prompt


def normalize_productcode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Product catalog must be a JSON array")
    catalog = {}
    for record in records:
        code = normalize_productcode(record.get("productcode"))
        if code:
            catalog.setdefault(code, record)
    return catalog


def fallback_group(name: str) -> str:
    try:
        groups = group_products([name])
    except ValueError:
        return "other"
    return next(key for key, items in groups.items() if items)


def catalog_metric(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return result if result.is_finite() else Decimal(0)


def resolve_and_rank(
    productcodes: list[str],
    catalog: dict[str, dict[str, Any]],
    *, category_groups: dict[str, dict] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    category_groups = (
        load_category_groups() if category_groups is None else category_groups
    )
    products = {}
    excluded = []
    codes = dict.fromkeys(normalize_productcode(code) for code in productcodes)
    for code in codes:
        if not code:
            excluded.append({"productcode": "", "reason": "missing_code"})
            continue
        record = catalog.get(code)
        if record is None:
            excluded.append({
                "productcode": code, "reason": "catalog_not_found",
            })
            continue
        name = str(record.get("tên sản phẩm") or "").strip()
        if not name:
            excluded.append({"productcode": code, "reason": "missing_name"})
            continue
        fallback = fallback_group(name)
        if fallback in ("telecom", "vouchers", "services"):
            excluded.append({"productcode": code, "reason": fallback})
            continue
        category_id = str(record.get("category_id") or "").strip()
        category_name = str(record.get("category_name") or "Sản phẩm khác")
        display_group = category_groups.get(category_id)
        if display_group is None:
            display_group = category_groups["__other__"]
        if not display_group["generate_image"]:
            excluded.append({
                "productcode": code, "reason": display_group["group_id"],
            })
            continue
        if code not in products:
            products[code] = {
                "productcode": code, "name": name,
                "color": str(record.get("màu sắc") or "").strip(),
                "brand": str(record.get("brand") or "").strip(),
                "category_id": category_id, "category_name": category_name,
                "group_id": display_group["group_id"],
                "group_name": display_group["group_name"],
                "url_image": str(record.get("url_image") or "").strip(),
                "preserve_interior": display_group.get(
                    "preserve_interior", False,
                ),
                "scale": product_scale(
                    name, float(display_group.get("scale", 0.75)),
                ),
                "lookup_source": "catalog",
                "quantity_sold": catalog_metric(record.get("quantity_sold")),
                "rating_vote": catalog_metric(record.get("rating_vote")),
            }
    ranked = sorted(products.values(), key=lambda product: (
        -product["quantity_sold"], -product["rating_vote"],
        product["productcode"],
    ))
    for product in ranked:
        for key in ("quantity_sold", "rating_vote"):
            product[key] = str(product[key])
    return ranked, excluded


def normalized_product_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def product_variant_key(product: dict[str, Any]) -> tuple[str, ...]:
    return tuple(normalized_product_text(product[key]) for key in (
        "group_id", "brand", "name", "color",
    ))


def build_catalog_plan(
    productcodes: list[str],
    catalog: dict[str, dict[str, Any]],
    *,
    category_groups: dict[str, dict] | None = None,
    image_size: str | None = None,
    steps: int | None = None,
    cfg: float | None = None,
) -> dict[str, Any]:
    from src.core.config import settings

    target_size = image_size or settings.IMAGE_SIZE
    target_steps = steps if steps is not None else settings.IMAGE_STEPS
    target_cfg = cfg if cfg is not None else settings.IMAGE_CFG

    ranked, excluded = resolve_and_rank(
        productcodes, catalog, category_groups=category_groups,
    )
    categories = {}
    seen_variants = {}
    duplicates = []
    for product in ranked:
        identity = product_variant_key(product)
        if identity in seen_variants:
            original = seen_variants[identity]
            original["productcodes"].append(product["productcode"])
            duplicates.append({
                "productcode": product["productcode"],
                "duplicate_of": original["productcode"],
            })
            continue
        product["productcodes"] = [product["productcode"]]
        seen_variants[identity] = product
        category_id = product["group_id"]
        category = categories.setdefault(category_id, {
            "id": category_id,
            "key": "category_" + hashlib.sha256(
                category_id.encode("utf-8"),
            ).hexdigest()[:16],
            "name": product["group_name"], "products": [],
            "selected_products": [],
        })
        category["products"].append(product)
        category["selected_products"].append(product)

    result = []
    requests = {}
    groups = {}
    for category in categories.values():
        selected = category["selected_products"]
        if not selected:
            continue
        category["source_categories"] = list({
            product["category_id"]: {
                "id": product["category_id"], "name": product["category_name"],
            }
            for product in category["products"]
        }.values())
        category["order"] = len(result)
        category["omitted_count"] = 0
        category["scale"] = max(
            float(item.get("scale", 0.75)) for item in selected
        )
        result.append(category)
        groups[category["key"]] = [item["name"] for item in selected]
        group_products = selected[:3]
        image_urls = [
            item["url_image"] for item in group_products
            if item.get("url_image")
        ][:3]
        key = category["key"]
        category["request_keys"] = [key]
        category["request_settings"] = {
            key: {
                "productcode": group_products[0]["productcode"],
                "productcodes": [
                    item["productcode"] for item in group_products
                ],
                "preserve_interior": any(
                    bool(item.get("preserve_interior"))
                    for item in group_products
                ),
                "scale": category["scale"],
            }
        }
        prompt = build_group_edit_prompt(group_products)
        requests[key] = {
            "prompt": prompt,
            "images": image_urls,
            "size": target_size,
            "n": 1,
            "steps": target_steps,
            "cfg": target_cfg,
        }

    return {
        "version": 5,
        "ranking": "quantity_sold_desc,rating_vote_desc,productcode",
        "categories": result, "groups": groups, "requests": requests,
        "excluded": excluded, "duplicates": duplicates,
    }
