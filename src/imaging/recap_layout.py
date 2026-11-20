# Place generated product groups and Vietnamese labels on the recap background.

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from src.core.paths import BACKGROUND_DIR
from src.imaging.background_templates import (
    GROUPS_PER_PAGE, IMAGE_SLOTS_BY_COUNT, background_for_groups,
)
from src.imaging.product_cutout import (
    remove_product_background, save_product_cutout,
)
from src.imaging.recap_badges import draw_category_badge

LEGACY_CATEGORY_LABELS = {
    'appliances': 'Điện gia dụng\n& Thiết bị nhà bếp',
    'phones': 'Điện thoại\n& Máy tính bảng',
    'accessories': 'Thiết bị thông minh\n& Phụ kiện',
    'household': 'Đồ gia dụng\n& Tiêu dùng',
    'healthcare': 'Chăm sóc sức khỏe',
    'telecom': 'Thẻ cào & Dịch vụ\nviễn thông',
    'vouchers': 'Phiếu mua hàng\n& Ưu đãi',
    'services': 'Dịch vụ\n(Giao hàng, Lắp đặt)',
}


def find_font() -> Path:
    """Find a font with Vietnamese glyphs, or use RECAP_FONT_PATH."""
    configured = os.getenv("RECAP_FONT_PATH")
    candidates = [Path(configured)] if configured else [
        BACKGROUND_DIR / "Pacifico-Regular.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Set RECAP_FONT_PATH to a Vietnamese-capable .ttf font"
    )


BADGE_SCALE = 1.38


def _scaled_badge_boxes(
    badges: list[
        tuple[tuple[int, int, int, int], str, str]
        | tuple[tuple[int, int, int, int], str, str, float]
    ],
) -> list[tuple[tuple[int, int, int, int], str, str, float]]:
    centers = [
        [(item[0][0] + item[0][2]) / 2, (item[0][1] + item[0][3]) / 2]
        for item in badges
    ]
    scaled = []
    for index, item in enumerate(badges):
        if len(item) == 4:
            box, label, group_id, angle = item
        else:
            box, label, group_id = item
            angle = 0.0
        cx, cy = centers[index]
        scale = 1.0 if len(item) == 4 else BADGE_SCALE
        width = min(380.0, (box[2] - box[0]) * scale)
        height = (box[3] - box[1]) * scale
        if angle == 0 and len(item) != 4:
            for other_index in range(len(badges)):
                if index == other_index:
                    continue
                other_cx, other_cy = centers[other_index]
                if abs(cy - other_cy) < height * 0.9:
                    width = min(width, abs(cx - other_cx) - 8)
        scaled.append(((
            max(8, round(cx - width / 2)),
            round(cy - height / 2),
            min(1016, round(cx + width / 2)),
            round(cy + height / 2),
        ), label, group_id, angle))
    return scaled


BADGE_ASSET_ALIASES = {
    "phones": "phones_tablets",
    "accessories": "smart_accessories",
    "appliances": "appliances_kitchen",
    "healthcare": "health_personal_care",
    "computers": "computers_office",
    "tools": "tools_lighting",
    "fashion": "fashion_sports_travel",
}


def _find_badge_asset(group_id: str) -> Path | None:
    canonical = BADGE_ASSET_ALIASES.get(group_id, group_id)
    for name in (group_id, canonical):
        path = BACKGROUND_DIR / "badges" / f"{name}.png"
        if path.is_file():
            return path
    return None


def _paste_badge_asset(
    image: Image.Image,
    pixel_box: tuple[int, int, int, int],
    asset_path: Path,
    angle: float = 0.0,
) -> None:
    left, top, right, bottom = pixel_box
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    target_w = max(1, right - left)
    with Image.open(asset_path) as source:
        badge = source.convert("RGBA")
        aspect = badge.height / max(1, badge.width)
        target_h = round(target_w * aspect)
        badge_resized = badge.resize(
            (target_w, target_h), Image.Resampling.LANCZOS,
        )
        if angle != 0.0:
            badge_rot = badge_resized.rotate(
                angle, resample=Image.Resampling.BICUBIC, expand=True,
            )
        else:
            badge_rot = badge_resized
        px = cx - badge_rot.width // 2
        py = cy - badge_rot.height // 2

        shadow = Image.new("RGBA", image.size)
        shadow.paste(
            (25, 18, 65, 95), (px, py + 3), badge_rot.getchannel("A"),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(3))
        image.paste(shadow, (0, 0), shadow)
        image.paste(badge_rot, (px, py), badge_rot)


def render_category_badges(
    image_path: Path, *,
    badges: list[
        tuple[tuple[int, int, int, int], str, str]
        | tuple[tuple[int, int, int, int], str, str, float]
    ],
    font_path: Path | None = None,
) -> Path:
    """Add only category badges; the background owns its header and frame."""
    font_path = find_font() if font_path is None else font_path
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    scale_x = image.width / 1024
    scale_y = image.height / 1024
    scaled_boxes = _scaled_badge_boxes(badges)
    scaled_boxes.sort(key=lambda item: item[0][1] + item[0][3])
    for box, label, group_id, angle in scaled_boxes:
        pixel_box = (
            round(box[0] * scale_x), round(box[1] * scale_y),
            round(box[2] * scale_x), round(box[3] * scale_y),
        )
        badge_asset = _find_badge_asset(group_id)
        if badge_asset is not None:
            _paste_badge_asset(image, pixel_box, badge_asset, angle=angle)
        else:
            draw_category_badge(
                image, pixel_box, label, group_id, font_path, angle=angle,
            )
    output_path = image_path.with_name(f"{image_path.stem}_final.png")
    image.save(output_path)
    return output_path


def prepare_product_image(source: Image.Image) -> Image.Image:
    """Remove an opaque backdrop, then crop the transparent outer margins."""
    image = remove_product_background(source)
    bounds = image.getchannel("A").point(
        lambda value: 255 if value > 16 else 0,
    ).getbbox()
    if bounds is None:
        return image
    # Large transparent margins lift products away from the podium surface.
    padding = 2
    left, top, right, bottom = bounds
    return image.crop((
        max(0, left - padding), max(0, top - padding),
        min(image.width, right + padding), min(image.height, bottom + padding),
    ))


GROUP_SLOT_INDEX_7 = {
    "smart_accessories": 0,
    "computers_office": 1,
    "health_personal_care": 2,
    "appliances_kitchen": 3,
    "tools_lighting": 4,
    "fashion_sports_travel": 4,
    "household": 5,
    "phones_tablets": 6,
}
GROUP_BADGES_7 = {
    "smart_accessories": (715, 240, 970, 300),
    "computers_office": (75, 395, 315, 455),
    "health_personal_care": (355, 405, 620, 465),
    "appliances_kitchen": (675, 500, 915, 560),
    "tools_lighting": (85, 620, 325, 680),
    "fashion_sports_travel": (85, 620, 325, 680),
    "household": (380, 675, 640, 735),
    "phones_tablets": (690, 690, 950, 750),
}


GROUP_SLOT_INDEX_8 = {
    "computers_office": 0,
    "smart_accessories": 1,
    "fashion_sports_travel": 2,
    "health_personal_care": 3,
    "appliances_kitchen": 4,
    "tools_lighting": 5,
    "household": 6,
    "phones_tablets": 7,
}
GROUP_BADGES_8 = {
    "computers_office": (337, 344, 512, 400),
    "smart_accessories": (655, 329, 835, 387),
    "fashion_sports_travel": (112, 452, 287, 508),
    "health_personal_care": (450, 474, 625, 530),
    "appliances_kitchen": (722, 503, 902, 561),
    "tools_lighting": (162, 610, 337, 666),
    "household": (417, 714, 592, 770),
    "phones_tablets": (695, 641, 875, 699),
}
GROUP_BADGE_ANGLES_8 = {
    "computers_office": -5.0,
    "smart_accessories": 20.0,
    "fashion_sports_travel": 0.0,
    "health_personal_care": 0.0,
    "appliances_kitchen": 17.0,
    "tools_lighting": 0.0,
    "household": 0.0,
    "phones_tablets": -13.5,
}
GROUP_SLOTS_8 = {
    "computers_office": (315, 195, 535, 360),
    "smart_accessories": (665, 175, 875, 345),
    "fashion_sports_travel": (105, 305, 315, 470),
    "health_personal_care": (425, 360, 645, 490),
    "appliances_kitchen": (715, 370, 915, 515),
    "tools_lighting": (140, 490, 360, 625),
    "household": (395, 565, 615, 725),
    "phones_tablets": (670, 510, 890, 650),
}
GROUP_SLOT_TILTS_8 = {
    "computers_office": -5.0,
    "smart_accessories": 18.0,
    "fashion_sports_travel": 0.0,
    "health_personal_care": 0.0,
    "appliances_kitchen": 16.0,
    "tools_lighting": 0.0,
    "household": 0.0,
    "phones_tablets": -13.0,
}
SLOT_BADGES_3 = (
    ((635, 505, 845, 575), 15.0),
    ((210, 590, 425, 650), -15.0),
    ((650, 700, 865, 760), 15.0),
)
SLOT_BADGES_4 = (
    ((395, 460, 595, 520), 12.0),
    ((150, 570, 315, 625), -12.0),
    ((635, 575, 845, 630), 15.0),
    ((370, 700, 580, 755), 16.0),
)


def category_layout(
    names: dict[str, str],
    *, category_icons: dict[str, str] | None = None,
) -> list[dict]:
    """Use the same ordered slot for a category's image and its label."""
    count = len(names)
    if not 1 <= count <= GROUPS_PER_PAGE:
        raise ValueError(
            f"A recap page must contain 1-{GROUPS_PER_PAGE} groups"
        )
    result = []
    slots = list(IMAGE_SLOTS_BY_COUNT[count])
    if count == 3:
        for (key, name), slot, (badge, angle) in zip(
            names.items(), slots, SLOT_BADGES_3,
        ):
            result.append({
                "key": key, "slot": slot, "badge": badge, "label": name,
                "angle": angle, "tilt": 0.0,
            })
        return result
    if count == 4:
        for (key, name), slot, (badge, angle) in zip(
            names.items(), slots, SLOT_BADGES_4,
        ):
            result.append({
                "key": key, "slot": slot, "badge": badge, "label": name,
                "angle": angle, "tilt": 0.0,
            })
        return result
    if count in (7, 8) and category_icons:
        mapping = GROUP_SLOT_INDEX_8 if count == 8 else GROUP_SLOT_INDEX_7
        badge_map = GROUP_BADGES_8 if count == 8 else GROUP_BADGES_7
        assigned: dict[str, tuple[int, tuple[int, int, int, int]]] = {}
        used = set()
        for key in names:
            group_id = category_icons.get(key, key)
            idx = mapping.get(group_id)
            if idx is not None and idx not in used:
                slot = (
                    GROUP_SLOTS_8.get(group_id, slots[idx]) if count == 8
                    else slots[idx]
                )
                assigned[key] = (idx, slot)
                used.add(idx)
        remaining = [i for i in range(count) if i not in used]
        for key in names:
            if key not in assigned:
                idx = remaining.pop(0)
                assigned[key] = (idx, slots[idx])
                used.add(idx)
        for key, name in names.items():
            idx, slot = assigned[key]
            group_id = category_icons.get(key, key)
            badge = badge_map.get(group_id)
            angle = 0.0
            tilt = 0.0
            if count == 8:
                angle = GROUP_BADGE_ANGLES_8.get(group_id, 0.0)
                tilt = GROUP_SLOT_TILTS_8.get(group_id, 0.0)
            if badge is None:
                left, top, right, bottom = slot
                badge = (left, bottom - 16, right, bottom + 40)
            result.append({
                "key": key, "slot": slot, "badge": badge, "label": name,
                "angle": angle, "tilt": tilt,
            })
        return result
    for (key, name), slot in zip(names.items(), slots):
        left, top, right, bottom = slot
        badge = (left, bottom - 16, right, bottom + 40)
        result.append({
            "key": key, "slot": (left, top, right, bottom),
            "badge": badge, "label": name, "angle": 0.0, "tilt": 0.0,
        })
    return result


def _slot_target_size(
    product: Image.Image,
    slot_size: tuple[int, int],
    *,
    group_scale: float | None,
    item_count: int,
) -> tuple[int, int]:
    width, height = slot_size
    if group_scale is None:
        return max(1, width), max(1, height)
    scale = max(0.45, min(1.0, float(group_scale)))
    aspect = product.width / max(1, product.height)
    scale_factor = 0.72 + 0.28 * scale
    if item_count <= 1:
        max_w = width * (0.65 + 0.35 * scale)
        max_h = min(height * 0.88, width * 0.68) * scale_factor
        if aspect > 1.8:
            max_w *= 0.88
        elif aspect < 0.55:
            max_h *= 0.88
    else:
        max_w = width * min(1.0, 0.84 + 0.16 * scale)
        max_h = min(height * 0.90, width * 0.72) * scale_factor
    return max(1, round(max_w)), max(1, round(max_h))


def compose_recap(
    assets: dict[str, Path],
    groups: dict[str, list[str]],
    output_path: Path,
    *, category_names: dict[str, str] | None = None,
    category_icons: dict[str, str] | None = None,
    category_scales: dict[str, float] | None = None,
    background_path: Path | None = None,
) -> Path:
    """Build the scene in code; generated images stay inside their slots."""
    if category_names is None:
        category_names = {
            key: LEGACY_CATEGORY_LABELS.get(key, key)
            for key, products in groups.items()
            if products
        }
    layout = category_layout(category_names, category_icons=category_icons)
    if background_path is None:
        background_path = background_for_groups(len(layout))
    font_path = find_font()
    with Image.open(background_path) as background:
        image = background.convert("RGB")
    scale_x = image.width / 1024
    scale_y = image.height / 1024
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 28)
    for item in sorted(layout, key=lambda it: it["slot"][3]):
        key = item["key"]
        slot = item["slot"]
        left, top, right, bottom = (
            round(slot[0] * scale_x), round(slot[1] * scale_y),
            round(slot[2] * scale_x), round(slot[3] * scale_y),
        )
        if key in assets:
            cutout_path = save_product_cutout(assets[key])
            slot_size = (right - left, bottom - top)
            group_scale = (
                None if category_scales is None
                else category_scales.get(key, 1.0)
            )
            item_count = len(groups.get(key, ())) or 1
            with Image.open(cutout_path) as source:
                product = prepare_product_image(source)
                target_size = _slot_target_size(
                    product, slot_size,
                    group_scale=group_scale, item_count=item_count,
                )
                thumbnail = ImageOps.contain(
                    product, target_size,
                    Image.Resampling.LANCZOS,
                )
            tilt = item.get("tilt", 0.0)
            if tilt != 0.0:
                thumbnail = thumbnail.rotate(
                    tilt, resample=Image.Resampling.BICUBIC, expand=True,
                )
            position = (
                left + (right - left - thumbnail.width) // 2,
                bottom - thumbnail.height,
            )
            shadow = Image.new("RGBA", image.size)
            center = position[0] + thumbnail.width // 2
            radius = thumbnail.width * 0.35
            ImageDraw.Draw(shadow).ellipse(
                (center - radius, bottom - 5,
                 center + radius, bottom + 5),
                fill=(25, 20, 65, 55),
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(4))
            image.paste(shadow, (0, 0), shadow)
            # Composite only product alpha; there is no card or image border.
            image.paste(thumbnail, position, thumbnail)
        elif groups[key] and key in ("telecom", "vouchers", "services"):
            center = (left + right) // 2
            if key == "services":
                draw.rectangle(
                    (center - 75, top + 25, center + 20, bottom - 20),
                    fill="#fff6cf", outline="#ffcc48", width=3,
                )
                draw.rectangle(
                    (center + 20, top + 45, center + 75, bottom - 20),
                    fill="#ffcf50", outline="#fff6cf", width=3,
                )
                for x in (center - 45, center + 50):
                    draw.ellipse(
                        (x - 14, bottom - 32, x + 14, bottom - 4),
                        fill="#142567",
                    )
            else:
                for offset in (-30, 15):
                    draw.rounded_rectangle(
                        (center - 75 + offset, top + 10,
                         center + 45 + offset, bottom - 8),
                        radius=12,
                        fill="#ffdb67" if key == "vouchers" else "#4c94f6",
                        outline="#fff5d4", width=3,
                    )
                symbol = "%" if key == "vouchers" else "SIM"
                draw.text(
                    (center, (top + bottom) // 2), symbol,
                    anchor="mm", font=font, fill="#07165f",
                )
        elif groups[key]:
            raise ValueError(f"Missing generated image for group: {key}")
        else:
            draw.text(
                ((left + right) // 2, (top + bottom) // 2),
                "Không có sản phẩm", anchor="mm", font=font, fill="white",
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    # The supplied background already contains its own header and podiums.
    return render_category_badges(
        output_path, font_path=font_path,
        badges=[
            (item["badge"], item["label"],
             (category_icons or {}).get(item["key"], item["key"]),
             item.get("angle", 0.0))
            for item in layout
        ],
    )
