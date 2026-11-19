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


BADGE_SCALE = 1.5


def _scaled_badge_boxes(
    badges: list[tuple[tuple[int, int, int, int], str, str]],
) -> list[tuple[tuple[int, int, int, int], str, str]]:
    centers = [
        [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
        for box, _, _ in badges
    ]
    for index, (cx, cy) in enumerate(centers):
        row = [
            other for other in range(len(badges))
            if abs(centers[other][1] - cy) < 56
        ]
        if len(row) == 3:
            ordered = sorted(row, key=lambda item: centers[item][0])
            if index == ordered[0]:
                centers[index][0] = max(155.0, cx - 16.0)
            elif index == ordered[2]:
                centers[index][0] = min(869.0, cx + 16.0)
    scaled = []
    for index, (box, label, group_id) in enumerate(badges):
        cx, cy = centers[index]
        width = (box[2] - box[0]) * BADGE_SCALE
        height = (box[3] - box[1]) * BADGE_SCALE
        for other_index in range(len(badges)):
            if index == other_index:
                continue
            other_cx, other_cy = centers[other_index]
            if abs(cy - other_cy) < height:
                width = min(width, abs(cx - other_cx) - 6)
        scaled.append(((
            max(8, round(cx - width / 2)),
            round(cy - height / 2),
            min(1016, round(cx + width / 2)),
            round(cy + height / 2),
        ), label, group_id))
    return scaled


def render_category_badges(
    image_path: Path, *,
    badges: list[tuple[tuple[int, int, int, int], str, str]],
    font_path: Path | None = None,
) -> Path:
    """Add only category badges; the background owns its header and frame."""
    font_path = find_font() if font_path is None else font_path
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    scale_x = image.width / 1024
    scale_y = image.height / 1024
    for box, label, group_id in _scaled_badge_boxes(badges):
        pixel_box = (
            round(box[0] * scale_x), round(box[1] * scale_y),
            round(box[2] * scale_x), round(box[3] * scale_y),
        )
        draw_category_badge(image, pixel_box, label, group_id, font_path)
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


def category_layout(names: dict[str, str]) -> list[dict]:
    """Use the same ordered slot for a category's image and its label."""
    count = len(names)
    if not 1 <= count <= GROUPS_PER_PAGE:
        raise ValueError(
            f"A recap page must contain 1-{GROUPS_PER_PAGE} groups"
        )
    result = []
    for (key, name), slot in zip(names.items(), IMAGE_SLOTS_BY_COUNT[count]):
        left, top, right, bottom = slot
        result.append({
            "key": key, "slot": (left, top, right, bottom),
            "badge": (left, bottom - 16, right, bottom + 40), "label": name,
        })
    return result


def compose_recap(
    assets: dict[str, Path],
    groups: dict[str, list[str]],
    output_path: Path,
    *, category_names: dict[str, str] | None = None,
    category_icons: dict[str, str] | None = None,
    background_path: Path | None = None,
) -> Path:
    """Build the scene in code; generated images stay inside their slots."""
    if category_names is None:
        category_names = {
            key: LEGACY_CATEGORY_LABELS.get(key, key)
            for key, products in groups.items()
            if products
        }
    layout = category_layout(category_names)
    if background_path is None:
        background_path = background_for_groups(len(layout))
    font_path = find_font()
    with Image.open(background_path) as background:
        image = background.convert("RGB")
    scale_x = image.width / 1024
    scale_y = image.height / 1024
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 28)
    for item in layout:
        key = item["key"]
        slot = item["slot"]
        left, top, right, bottom = (
            round(slot[0] * scale_x), round(slot[1] * scale_y),
            round(slot[2] * scale_x), round(slot[3] * scale_y),
        )
        if key in assets:
            cutout_path = save_product_cutout(assets[key])
            with Image.open(cutout_path) as source:
                product = prepare_product_image(source)
                thumbnail = ImageOps.contain(
                    product, (right - left, bottom - top),
                    Image.Resampling.LANCZOS,
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
             (category_icons or {}).get(item["key"], item["key"]))
            for item in layout
        ],
    )
