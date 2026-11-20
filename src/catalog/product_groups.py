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
DEFAULT_GROUP_SCALES = {
    "phones_tablets": 0.78,
    "computers_office": 0.82,
    "smart_accessories": 0.60,
    "appliances_kitchen": 0.88,
    "household": 0.72,
    "health_personal_care": 0.66,
    "fashion_sports_travel": 0.78,
    "tools_lighting": 0.68,
    "services": 0.60,
    "other": 0.75,
}
CATEGORY_SCALES = {
    # XL: Floor-standing appliances, large furniture, bikes, water tanks (1.0)
    **dict.fromkeys((
        "36", "37", "38", "39", "40", "46", "72", "96", "115", "116",
        "117", "157", "193", "194", "199", "200", "304", "316", "321",
        "329", "333",
    ), 1.0),
    # L: Laptops, monitors, tablets, suitcases, large countertop devices
    "28": 0.94, "30": 0.88, "41": 0.84, "44": 0.92, "73": 0.95,
    "75": 0.85, "77": 0.80, "79": 0.82, "86": 0.78, "87": 0.80,
    "91": 0.86, "103": 0.86, "106": 0.90, "147": 0.80, "162": 0.86,
    "163": 0.86, "165": 0.86, "166": 0.78, "167": 0.84, "168": 0.84,
    "169": 0.80, "170": 0.82, "171": 0.80, "184": 0.88, "198": 0.90,
    "201": 0.86, "207": 0.88, "218": 0.85, "255": 0.85, "256": 0.85,
    "267": 0.82, "271": 0.82, "303": 0.78, "311": 0.82, "322": 0.85,
    "330": 0.80,
    # M: Phones, medium kitchenware, power tools, bags, speakers
    "27": 0.68, "59": 0.78, "66": 0.70, "71": 0.74, "80": 0.72,
    "97": 0.72, "98": 0.74, "99": 0.70, "100": 0.70, "101": 0.68,
    "102": 0.72, "104": 0.68, "105": 0.72, "114": 0.72, "127": 0.64,
    "130": 0.72, "132": 0.76, "135": 0.70, "152": 0.70, "156": 0.70,
    "161": 0.76, "172": 0.62, "185": 0.70, "186": 0.66, "187": 0.68,
    "202": 0.70, "205": 0.72, "206": 0.72, "211": 0.70, "212": 0.66,
    "224": 0.74, "226": 0.74, "231": 0.72, "241": 0.72, "244": 0.76,
    "251": 0.68, "261": 0.74, "268": 0.66, "269": 0.74, "274": 0.68,
    "275": 0.64, "276": 0.64, "279": 0.66, "280": 0.70, "283": 0.66,
    "301": 0.72, "302": 0.66, "306": 0.68, "312": 0.64, "313": 0.66,
    "318": 0.66, "319": 0.68, "320": 0.62, "331": 0.68,
    # S: Compact accessories, handheld personal care, small hand tools
    **dict.fromkeys((
        "49", "50", "51", "57", "58", "60", "63", "64", "65", "68",
        "69", "70", "74", "76", "82", "83", "93", "118", "119", "120",
        "121", "122", "123", "124", "125", "126", "128", "129", "133",
        "134", "136", "137", "139", "140", "141", "142", "148", "149",
        "151", "158", "160", "164", "174", "175", "176", "177", "178",
        "179", "180", "181", "182", "183", "203", "208", "210", "213",
        "215", "216", "220", "221", "222", "223", "232", "236", "238",
        "250", "253", "257", "278", "282", "284", "285", "293", "297",
        "307", "309", "317", "323", "324", "325", "326",
    ), 0.52),
}


def product_scale(name: str, base_scale: float = 0.75) -> float:
    """Refine category scale using explicit size tokens in a product name."""
    scale = float(base_scale)
    lowered = name.casefold()
    if "quạt tản nhiệt điện thoại" in lowered:
        scale = min(scale, 0.46)
    elif "mini" in lowered:
        scale *= 0.86
    if "size xs" in lowered:
        scale *= 0.85
    elif "size s" in lowered:
        scale *= 0.92
    elif "size xl" in lowered or "size l" in lowered:
        scale *= 1.06
    return round(max(0.42, min(1.0, scale)), 2)


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
            "scale": DEFAULT_GROUP_SCALES.get(group_id, 0.75),
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
        default_scale = CATEGORY_SCALES.get(
            category_id, groups[group_id]["scale"],
        )
        scale = label.get("scale", default_scale)
        if (
            isinstance(scale, bool)
            or not isinstance(scale, (int, float))
            or not 0.30 <= float(scale) <= 1.0
        ):
            raise ValueError(f"scale must be in [0.30, 1.0]: {category_id}")
        labels[category_id] = {
            "category_id": category_id, "category_name": label["name"],
            **groups[group_id], "preserve_interior": preserve_interior,
            "scale": float(scale),
        }
    return labels
