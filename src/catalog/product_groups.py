# Load category-to-recap groups and detect nonphysical purchase names.

from pathlib import Path

import yaml

from src.core.paths import CATEGORY_LABELS_PATH

GROUP_KEYS = (
    "appliances", "phones", "accessories", "household", "healthcare",
    "telecom", "vouchers", "services",
)
GROUP_RULES = (
    ("vouchers", ("pmh", "phiếu mua hàng")),
    ("telecom", ("airtime", "thẻ cào")),
    ("services", ("dịch vụ", "lắp đặt", "tặng combo vật tư")),
    ("accessories", (
        "thẻ nhớ", "camera", "đồng hồ", "tai nghe", "miếng dán",
        "bút cảm ứng", "adapter", "pin aa",
    )),
    ("phones", ("điện thoại", "máy tính bảng", "iphone", "ipad", "oppo")),
    ("healthcare", ("prospan", "refresh", "flumetholon", "thuốc")),
    ("appliances", (
        "máy lọc nước", "bếp điện", "bình đun", "quạt", "máy lạnh",
    )),
    ("household", ("bình giữ nhiệt", "bộ nồi", "bộ lau", "ly nhựa", "sữa")),
)


def group_products(products: list[str]) -> dict[str, list[str]]:
    """Fail on unknown items instead of silently placing them incorrectly."""
    groups = {key: [] for key in GROUP_KEYS}
    unmatched = []
    for product in products:
        name = product.casefold()
        for key, keywords in GROUP_RULES:
            if any(keyword in name for keyword in keywords):
                groups[key].append(product)
                break
        else:
            unmatched.append(product)
    if unmatched:
        raise ValueError(
            "Add classification rules for these products: "
            + "; ".join(unmatched)
        )
    return groups


def load_category_groups(path: Path = CATEGORY_LABELS_PATH) -> dict[str, dict]:
    """Resolve detailed category IDs to configurable recap display groups."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("version") != 2:
        raise ValueError("Category grouping YAML must use version 2")
    groups = {}
    for group in document["groups"]:
        group_id = group["id"]
        if group_id in groups:
            raise ValueError(f"Duplicate display group: {group_id}")
        if not isinstance(group.get("generate_image"), bool):
            raise ValueError(f"generate_image must be boolean: {group_id}")
        groups[group_id] = {
            "group_id": group_id, "group_name": group["name"],
            "generate_image": group["generate_image"],
        }
    if "other" not in groups:
        raise ValueError("Category groups must define an 'other' fallback")
    labels = {"__other__": groups["other"]}
    for label in document["labels"]:
        category_id = str(label["category_id"]).strip()
        group_id = label["group_id"]
        if category_id in labels:
            raise ValueError(f"Duplicate category ID: {category_id}")
        if group_id not in groups:
            raise ValueError(f"Undefined display group: {group_id}")
        preserve_interior = label.get("preserve_interior", False)
        if not isinstance(preserve_interior, bool):
            raise ValueError(
                f"preserve_interior must be boolean: {category_id}"
            )
        labels[category_id] = {
            "category_id": category_id, "category_name": label["name"],
            **groups[group_id], "preserve_interior": preserve_interior,
        }
    return labels
