# Verify text rendering preserves source images and output dimensions.

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from src.imaging.recap_layout import (
    category_layout, compose_recap, find_font, prepare_product_image,
    render_category_badges,
)


class RecapLayoutTests(unittest.TestCase):
    def test_each_page_uses_its_group_count_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "product.png"
            image = Image.new("RGBA", (100, 100))
            ImageDraw.Draw(image).rectangle((25, 10, 75, 90), fill="red")
            image.save(asset)
            groups = {str(i): [f"Product {i}"] for i in range(8)}
            for count in range(1, 9):
                with self.subTest(groups=count):
                    background = root / f"mwg-background-recap-{count}.png"
                    color = (count * 20, 100, 150)
                    Image.new("RGB", (656, 600), color).save(background)
                    original = background.read_bytes()
                    names = {str(i): f"Category {i}" for i in range(count)}
                    with patch(
                        "src.imaging.background_templates.BACKGROUND_DIR",
                        root,
                    ):
                        output = compose_recap(
                            {key: asset for key in names}, groups,
                            root / f"recap_{count}.png", category_names=names,
                        )
                    with Image.open(output) as result:
                        self.assertEqual(result.size, (656, 600))
                        self.assertEqual(result.getpixel((0, 0)), color)
                    self.assertEqual(background.read_bytes(), original)

    def test_legacy_plan_uses_only_nonempty_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background = root / "mwg-background-recap-1.png"
            Image.new("RGB", (656, 600), "navy").save(background)
            with patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ), patch(
                "src.imaging.recap_layout.render_category_badges",
            ) as render:
                compose_recap(
                    {}, {"phones": [], "telecom": ["SIM"]},
                    root / "recap.png",
                )
            self.assertEqual(len(render.call_args.kwargs["badges"]), 1)
            self.assertEqual(
                render.call_args.kwargs["badges"][0][2], "telecom",
            )

    def test_render_preserves_source_and_changes_label_regions(self):
        try:
            font_path = find_font()
        except FileNotFoundError:
            self.skipTest("No Vietnamese-capable font installed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            Image.new("RGB", (1024, 1024), "#5264c4").save(path)
            original = path.read_bytes()
            result = render_category_badges(
                path, font_path=font_path,
                badges=[((140, 412, 350, 475), "Điện thoại", "phones")],
            )
            self.assertNotEqual(result, path)
            self.assertEqual(path.read_bytes(), original)
            with Image.open(result) as image:
                self.assertEqual(image.size, (1024, 1024))
                self.assertEqual(image.getpixel((0, 0)), (82, 100, 196))
                self.assertEqual(image.getpixel((300, 100)), (82, 100, 196))
                self.assertNotEqual(image.getpixel((300, 440)), (82, 100, 196))

    def test_crop_preserves_white_surfaces_and_removes_studio_margins(self):
        image = Image.new("RGBA", (300, 300))
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 70, 200, 240), fill="black")
        draw.rectangle((115, 100, 185, 160), fill="white")
        result = prepare_product_image(image)
        self.assertLess(result.width, image.width)
        self.assertLess(result.height, image.height)
        self.assertEqual(result.getpixel((65, 65)), (255, 255, 255, 255))
        self.assertEqual(result.getextrema()[3], (0, 255))

    def test_crop_uses_existing_alpha_without_opaque_background(self):
        image = Image.new("RGBA", (300, 300))
        ImageDraw.Draw(image).rectangle((100, 100, 200, 200), fill="red")
        result = prepare_product_image(image)
        self.assertLess(result.width, image.width)
        self.assertEqual(result.getpixel((0, 0))[3], 0)

    def test_crop_keeps_product_feet_close_to_the_slot_baseline(self):
        image = Image.new("RGBA", (1024, 1024))
        ImageDraw.Draw(image).rectangle((200, 100, 800, 850), fill="red")
        result = prepare_product_image(image)
        bounds = result.getchannel("A").getbbox()
        self.assertLessEqual(result.height - bounds[3], 2)
        self.assertLessEqual(bounds[0], 2)

    def test_product_slots_clear_badges_on_the_podiums_above(self):
        for count in range(1, 9):
            layout = category_layout({str(i): str(i) for i in range(count)})
            for lower in layout:
                left, top, right, bottom = lower["slot"]
                for upper in layout:
                    above = upper["slot"][1] < top
                    badge = upper["badge"]
                    overlaps = left < badge[2] and right > badge[0]
                    if above and overlaps:
                        self.assertGreaterEqual(top, badge[3])

    def test_composition_preserves_background_size_header_and_source(self):
        try:
            find_font()
        except FileNotFoundError:
            self.skipTest("No Vietnamese-capable font installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background = root / "background.png"
            asset = root / "product.png"
            Image.new("RGB", (1312, 1199), "#284787").save(background)
            product = Image.new("RGBA", (100, 100))
            ImageDraw.Draw(product).ellipse((15, 15, 85, 85), fill="red")
            product.save(asset)
            original = background.read_bytes()
            result = compose_recap(
                {"phone": asset}, {"phone": ["Phone"]}, root / "recap.png",
                category_names={"phone": "Điện thoại"},
                background_path=background,
            )
            self.assertEqual(background.read_bytes(), original)
            with Image.open(result) as image, Image.open(background) as source:
                self.assertEqual(image.size, source.size)
                self.assertEqual(
                    image.crop((0, 0, 1312, 230)).tobytes(),
                    source.crop((0, 0, 1312, 230)).tobytes(),
                )
                self.assertEqual(image.getpixel((0, 1198)), (40, 71, 135))
                self.assertEqual(image.getpixel((510, 260)), (40, 71, 135))
                self.assertNotEqual(image.tobytes(), source.tobytes())

    def test_header_and_mascot_composited_over_products(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background = root / "background.png"
            header = root / "recap_header.png"
            mascot = root / "recap_mascot.png"
            asset = root / "product.png"

            # 1024x1024 blue background
            Image.new("RGB", (1024, 1024), (0, 0, 255)).save(background)
            # Solid yellow header
            Image.new("RGBA", (430, 285), (255, 255, 0, 255)).save(header)
            # Solid green mascot
            Image.new("RGBA", (180, 140), (0, 255, 0, 255)).save(mascot)
            # Solid red product cutout covering upper area
            Image.new("RGBA", (800, 800), (255, 0, 0, 255)).save(asset)

            result = compose_recap(
                {"phone": asset}, {"phone": ["Phone"]}, root / "recap.png",
                category_names={"phone": "Điện thoại"},
                background_path=background,
                header_path=header,
                mascot_path=mascot,
            )
            with Image.open(result) as image:
                # Header position (15, 0) inside (15, 0, 380, 242) -> yellow
                self.assertEqual(image.getpixel((100, 50)), (255, 255, 0))
                # Mascot at (560, 20) is inside (560, 20, 740, 160) -> green
                # Mascot must be composited ON TOP of product
                self.assertEqual(image.getpixel((600, 50)), (0, 255, 0))
