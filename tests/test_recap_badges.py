# Verify category badge icons, label wrapping and preservation of the image.

import unittest

from PIL import Image, ImageDraw, ImageFont

from src.imaging.recap_badges import (
    category_icon, draw_category_badge, wrap_label,
)
from src.imaging.recap_layout import find_font


class RecapBadgeTests(unittest.TestCase):
    def test_icons_cover_display_groups_with_distinct_shapes(self):
        groups = (
            "phones_tablets", "computers_office", "smart_accessories",
            "appliances_kitchen", "household", "health_personal_care",
            "fashion_sports_travel", "tools_lighting", "services",
        )
        icons = [category_icon(group, 48) for group in groups]
        self.assertEqual(len({icon.tobytes() for icon in icons}), len(groups))
        for icon in icons:
            self.assertEqual(icon.size, (48, 48))
            self.assertEqual(icon.mode, "RGBA")
            self.assertIsNotNone(icon.getbbox())
            self.assertEqual(icon.getpixel((0, 0))[3], 0)

    def test_label_breaks_at_ampersand_and_keeps_vietnamese(self):
        try:
            font_path = find_font()
        except FileNotFoundError:
            self.skipTest("No Vietnamese-capable font installed")
        image = Image.new("RGB", (400, 100))
        text = wrap_label(
            ImageDraw.Draw(image), "Điện thoại & Máy tính bảng",
            ImageFont.truetype(str(font_path), 20), 350,
        )
        self.assertEqual(text, "Điện thoại\n& Máy tính bảng")

    def test_badge_draws_icon_rim_and_label_without_changing_image_size(self):
        try:
            font_path = find_font()
        except FileNotFoundError:
            self.skipTest("No Vietnamese-capable font installed")
        image = Image.new("RGB", (500, 200), "#284787")
        draw_category_badge(
            image, (50, 60, 450, 140), "Điện thoại & Máy tính bảng",
            "phones_tablets", font_path,
        )
        self.assertEqual(image.size, (500, 200))
        self.assertEqual(image.getpixel((0, 0)), (40, 71, 135))
        r, g, b = image.getpixel((250, 62))
        self.assertTrue(r > 200 and 130 < g < r and b < 100)
        pill_pixels = [
            x for x in range(image.width)
            if image.getpixel((x, 100))[0] > 200
        ]
        left, right = min(pill_pixels), max(pill_pixels)
        self.assertLess(right - left, 350)
        self.assertAlmostEqual((left + right) / 2, 250, delta=2)
        icon_region = image.crop((left + 12, 70, left + 65, 130))
        navy_pixels = sum(
            1 for r, g, b in icon_region.get_flattened_data()
            if r < 30 and g < 40 and 60 < b < 140
        )
        self.assertGreater(navy_pixels, 20)
