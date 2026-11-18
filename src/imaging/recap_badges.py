# Draw Vietnamese category badges with gold rims and category-specific icons.

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NAVY = "#07165f"
ICON_NAMES = {
    "phones_tablets": "phone", "phones": "phone",
    "computers_office": "computer",
    "smart_accessories": "headphones", "accessories": "headphones",
    "appliances_kitchen": "house", "appliances": "house",
    "household": "basket", "health_personal_care": "cross",
    "healthcare": "cross", "fashion_sports_travel": "bag",
    "tools_lighting": "tools", "services": "gear",
    "telecom": "phone", "vouchers": "gift", "other": "bag",
}


def category_icon(group_id: str, size: int) -> Image.Image:
    """Render line icons at high resolution for smooth small-size output."""
    icon = Image.new("RGBA", (192, 192))
    draw = ImageDraw.Draw(icon)

    def coords(box):
        return tuple(round(value * 4) for value in box)

    def line(points):
        draw.line([(round(x * 4), round(y * 4)) for x, y in points],
                  fill=NAVY, width=11, joint="curve")

    def rectangle(box, radius=2):
        draw.rounded_rectangle(coords(box), radius=radius * 4,
                               outline=NAVY, width=11)

    def ellipse(box):
        draw.ellipse(coords(box), outline=NAVY, width=11)

    name = ICON_NAMES.get(group_id, "bag")
    if name == "phone":
        rectangle((13, 3, 35, 45), 3)
        line([(21, 7), (27, 7)])
        line([(22, 40), (26, 40)])
    elif name == "computer":
        rectangle((4, 7, 44, 33), 3)
        line([(24, 33), (24, 42)])
        line([(15, 42), (33, 42)])
    elif name == "house":
        line([(3, 23), (24, 5), (45, 23)])
        line([(9, 20), (9, 43), (20, 43), (20, 31),
              (28, 31), (28, 43), (39, 43), (39, 20)])
        line([(32, 9), (32, 4), (38, 4), (38, 14)])
    elif name == "headphones":
        draw.arc(coords((5, 5, 43, 43)), 180, 360, fill=NAVY, width=11)
        rectangle((4, 22, 13, 37), 3)
        rectangle((35, 22, 44, 37), 3)
        line([(40, 37), (36, 43), (26, 43)])
    elif name == "basket":
        line([(5, 19), (43, 19), (38, 43), (10, 43), (5, 19)])
        line([(14, 18), (20, 5)])
        line([(34, 18), (28, 5)])
        for x in (17, 24, 31):
            line([(x, 25), (x, 36)])
    elif name == "cross":
        line([(17, 5), (31, 5), (31, 17), (43, 17),
              (43, 31), (31, 31), (31, 43), (17, 43),
              (17, 31), (5, 31), (5, 17), (17, 17), (17, 5)])
    elif name == "tools":
        line([(9, 6), (39, 42)])
        line([(6, 9), (12, 3), (19, 12), (14, 17), (6, 9)])
        line([(8, 41), (28, 21)])
        draw.arc(coords((24, 3, 44, 23)), 30, 300, fill=NAVY, width=11)
        ellipse((5, 35, 13, 43))
    elif name == "gear":
        ellipse((11, 11, 37, 37))
        ellipse((19, 19, 29, 29))
        for a, b in (
            ((24, 4), (24, 11)), ((24, 37), (24, 44)),
            ((4, 24), (11, 24)), ((37, 24), (44, 24)),
            ((9, 9), (14, 14)), ((34, 34), (39, 39)),
            ((9, 39), (14, 34)), ((34, 14), (39, 9)),
        ):
            line([a, b])
    elif name == "gift":
        rectangle((7, 20, 41, 44))
        rectangle((4, 14, 44, 23))
        line([(24, 15), (24, 44)])
        ellipse((9, 3, 25, 15))
        ellipse((23, 3, 39, 15))
    else:
        rectangle((7, 15, 41, 43), 4)
        draw.arc(coords((15, 3, 33, 28)), 180, 360, fill=NAVY, width=11)
    return icon.resize((size, size), Image.Resampling.LANCZOS)


def wrap_label(draw, label, font, max_width):
    lines = []
    for paragraph in label.replace(" & ", "\n& ").splitlines():
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and draw.textlength(candidate, font=font) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return "\n".join(lines)


def draw_category_badge(
    image: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
    group_id: str,
    font_path: Path,
) -> None:
    """Draw a white pill, warm gold rim, navy icon and bold Vietnamese text."""
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    supersample = 3
    width_hi, height_hi = width * supersample, height * supersample
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    icon_size = round(height_hi * 0.60)
    icon_x = round(height_hi * 0.24)
    text_left = icon_x + icon_size + round(height_hi * 0.16)
    text_width = width_hi - text_left - icon_x
    size = max(1, round(height_hi * 0.36))
    spacing = max(1, round(height_hi * 0.025))
    # A slightly condensed treatment matches the reference while retaining
    # complete Vietnamese glyph coverage from the chosen bold font.
    condensed = 0.90
    while True:
        font = ImageFont.truetype(str(font_path), size)
        text = wrap_label(draw, label, font, text_width / condensed)
        bounds = draw.multiline_textbbox(
            (0, 0), text, font=font, spacing=spacing,
        )
        if (
            (bounds[2] - bounds[0]) * condensed <= text_width
            and bounds[3] - bounds[1] <= height_hi * 0.72
        ):
            break
        if size <= 1:
            raise ValueError("Category badge is too small for its label")
        size -= 1
    text_layer = Image.new("RGBA", (
        max(1, bounds[2] - bounds[0]), max(1, bounds[3] - bounds[1]),
    ))
    ImageDraw.Draw(text_layer).multiline_text(
        (-bounds[0], -bounds[1]), text, font=font, fill=NAVY, spacing=spacing,
    )
    text_layer = text_layer.resize((
        max(1, round(text_layer.width * condensed)), text_layer.height,
    ), Image.Resampling.LANCZOS)
    # Treat the supplied box as a maximum width, not a stretched pill.
    fitted_width = text_left + text_layer.width + icon_x
    fitted_width = min(width, max(
        height, (fitted_width + supersample - 1) // supersample,
    ))
    left += (width - fitted_width) // 2
    width = fitted_width
    width_hi = width * supersample
    radius = height_hi // 2
    badge = Image.new("RGBA", (width_hi, height_hi))
    mask = Image.new("L", badge.size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width_hi - 1, height_hi - 1), radius=radius, fill=255,
    )
    draw = ImageDraw.Draw(badge)
    for y in range(height_hi):
        t = y / max(1, height_hi - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(
            (255, 255, 255), (245, 242, 253),
        ))
        draw.line((0, y, width_hi, y), fill=color)
    badge.putalpha(mask)
    draw.rounded_rectangle(
        (2, 2, width_hi - 3, height_hi - 3), radius=radius,
        outline="#e9b529", width=3 * supersample,
    )
    inset = 4 * supersample
    draw.rounded_rectangle(
        (inset, inset, width_hi - inset, height_hi - inset),
        radius=radius - inset, outline="#fff0ad", width=supersample,
    )
    icon = category_icon(group_id, icon_size)
    badge.alpha_composite(icon, (icon_x, (height_hi - icon_size) // 2))
    badge.alpha_composite(text_layer, (
        text_left, (height_hi - text_layer.height) // 2,
    ))
    badge = badge.resize((width, height), Image.Resampling.LANCZOS)
    shadow = Image.new("RGBA", image.size)
    shadow.paste((33, 22, 83, 85), (left, top + 4), badge.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    image.paste(shadow, (0, 0), shadow)
    image.paste(badge, (left, top), badge)
