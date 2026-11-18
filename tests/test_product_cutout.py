# Verify alpha handling and local cutout caching without model downloads.

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

from src.imaging.product_cutout import (
    background_session, merge_product_cutouts, remove_product_background,
    restore_solid_interiors,
    save_product_cutout,
)


def transparent_product():
    image = Image.new("RGBA", (100, 100))
    ImageDraw.Draw(image).rectangle((25, 15, 75, 85), fill="white")
    return image


class ProductCutoutTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.model_path = Path(directory.name) / "model.onnx"
        self.model_path.write_bytes(b"model fixture")
        self.enterContext(patch(
            "src.imaging.product_cutout.BACKGROUND_MODEL_PATH",
            self.model_path,
        ))
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("REMBG_MODEL_PATH", None)

    def tearDown(self):
        background_session.cache_clear()

    def test_missing_model_fails_without_downloading(self):
        self.model_path.unlink()
        factory = MagicMock()
        with patch.dict(sys.modules, {
            "rembg": SimpleNamespace(new_session=factory),
        }):
            with self.assertRaisesRegex(FileNotFoundError, "REMBG_MODEL_PATH"):
                background_session()
        factory.assert_not_called()

    def test_explicit_model_path_is_loaded_directly(self):
        custom = self.model_path.with_name("custom.onnx")
        custom.write_bytes(b"model fixture")
        os.environ["REMBG_MODEL_PATH"] = str(custom)
        factory = MagicMock()
        with patch.dict(sys.modules, {
            "rembg": SimpleNamespace(new_session=factory),
        }):
            background_session()
        factory.assert_called_once_with(
            "dis_custom", model_path=str(custom.resolve()),
            providers=["CPUExecutionProvider"],
        )

    def test_existing_transparency_keeps_white_product_and_skips_model(self):
        source = transparent_product()
        fake_rembg = SimpleNamespace(
            remove=MagicMock(), new_session=MagicMock(),
        )
        with patch.dict(sys.modules, {"rembg": fake_rembg}):
            result = remove_product_background(source)
        self.assertEqual(result.tobytes(), source.tobytes())
        self.assertEqual(result.getpixel((50, 50)), (255, 255, 255, 255))
        fake_rembg.remove.assert_not_called()
        fake_rembg.new_session.assert_not_called()

    def test_opaque_images_use_one_local_cpu_session(self):
        cutout = transparent_product()
        fake_rembg = SimpleNamespace(
            remove=MagicMock(return_value=cutout), new_session=MagicMock(),
        )
        with patch.dict(sys.modules, {"rembg": fake_rembg}):
            first = remove_product_background(Image.new("RGB", (100, 100)))
            second = remove_product_background(Image.new("RGB", (100, 100)))
        self.assertEqual(first.mode, "RGBA")
        self.assertEqual(second.getchannel("A").getextrema(), (0, 255))
        fake_rembg.new_session.assert_called_once_with(
            "dis_custom", model_path=str(self.model_path.resolve()),
            providers=["CPUExecutionProvider"],
        )
        self.assertEqual(fake_rembg.remove.call_count, 2)

    def test_failed_segmentation_does_not_return_an_opaque_rectangle(self):
        fake_rembg = SimpleNamespace(
            remove=MagicMock(return_value=Image.new("RGB", (100, 100))),
            new_session=MagicMock(),
        )
        with patch.dict(sys.modules, {"rembg": fake_rembg}):
            with self.assertRaisesRegex(ValueError, "usable cutout"):
                remove_product_background(Image.new("RGB", (100, 100)))

    def test_cutout_cache_preserves_original_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "product.png"
            Image.new("RGB", (100, 100), "white").save(source)
            original = source.read_bytes()
            with patch(
                "src.imaging.product_cutout.remove_product_background",
                return_value=transparent_product(),
            ) as remove:
                first = save_product_cutout(source)
                second = save_product_cutout(source)
            self.assertEqual(first, second)
            self.assertNotEqual(first, source)
            self.assertEqual(source.read_bytes(), original)
            remove.assert_called_once()
            with Image.open(first) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getchannel("A").getextrema(), (0, 255))

    def test_merge_keeps_all_batch_images_on_transparent_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index, color in enumerate(("red", "blue", "green")):
                image = Image.new("RGBA", (100, 100))
                ImageDraw.Draw(image).rectangle((25, 15, 75, 85), fill=color)
                path = root / f"product_{index}.png"
                image.save(path)
                paths.append(path)
            output = merge_product_cutouts(paths, root / "group.png")
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                colors = set(image.get_flattened_data())
                for expected in ((255, 0, 0, 255), (0, 0, 255, 255),
                                 (0, 128, 0, 255)):
                    self.assertIn(expected, colors)

    def test_cluster_grounds_short_products_beside_tall_products(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, size, color in (
                ("tall", (140, 280), "red"),
                ("short", (240, 100), "blue"),
            ):
                image = Image.new("RGBA", (size[0] + 40, size[1] + 40))
                ImageDraw.Draw(image).rectangle(
                    (20, 20, size[0] + 19, size[1] + 19), fill=color,
                )
                path = root / f"{name}.png"
                image.save(path)
                paths.append(path)
            originals = [path.read_bytes() for path in paths]
            output = merge_product_cutouts(paths, root / "group.png")
            with Image.open(output) as image:
                pixels = image.load()
                bounds = []
                for color in ((255, 0, 0, 255), (0, 0, 255, 255)):
                    points = [
                        (x, y) for y in range(image.height)
                        for x in range(image.width) if pixels[x, y] == color
                    ]
                    bounds.append((
                        min(x for x, y in points), min(y for x, y in points),
                        max(x for x, y in points), max(y for x, y in points),
                    ))
                tall, short = bounds
                # The shorter product shares the floor, not a cell center.
                self.assertLess(abs(tall[3] - short[3]), 35)
                self.assertGreater(short[1], tall[1] + 100)
                self.assertGreater(short[2], tall[0])
                self.assertLess(short[2] - tall[0], 160)
                self.assertEqual(image.size, (1024, 1024))
            self.assertEqual(
                [path.read_bytes() for path in paths], originals,
            )

    def test_large_clusters_keep_each_product_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            colors = [
                (30 + index * 16, 200 - index * 12, 80, 255)
                for index in range(12)
            ]
            for index, color in enumerate(colors):
                image = Image.new("RGBA", (100, 140))
                ImageDraw.Draw(image).rectangle((15, 15, 85, 125), fill=color)
                path = root / f"product_{index}.png"
                image.save(path)
                paths.append(path)
            for count in (2, 3, 4, 5, 8, 12):
                with self.subTest(count=count):
                    output = merge_product_cutouts(
                        paths[:count], root / f"group_{count}.png",
                    )
                    with Image.open(output) as image:
                        visible = set(image.get_flattened_data())
                        self.assertTrue(set(colors[:count]) <= visible)
                        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_single_product_keeps_original_cutout(self):
        path = Path("single_cutout.png")
        self.assertEqual(
            merge_product_cutouts([path], Path("group.png")), path,
        )

    def test_solid_repair_keeps_device_face_and_exterior_transparency(self):
        source = Image.new("RGBA", (80, 100), "white")
        ImageDraw.Draw(source).rectangle((15, 10, 65, 90), fill="#333333")
        ImageDraw.Draw(source).rectangle((25, 25, 55, 65), fill="white")
        cutout = source.copy()
        alpha = Image.new("L", source.size)
        draw = ImageDraw.Draw(alpha)
        draw.rectangle((15, 10, 65, 90), fill=255)
        draw.rectangle((25, 25, 55, 65), fill=0)
        cutout.putalpha(alpha)
        repaired = restore_solid_interiors(source, cutout)
        self.assertEqual(repaired.getpixel((40, 40)), (255, 255, 255, 255))
        self.assertEqual(repaired.getpixel((0, 0))[3], 0)
        self.assertEqual(cutout.getpixel((40, 40))[3], 0)

    def test_mask_repair_is_opt_in_for_segmentation_only(self):
        source = Image.new("RGB", (100, 100), "white")
        result = transparent_product()
        ImageDraw.Draw(result).rectangle((40, 30, 60, 60), fill=(0, 0, 0, 0))
        fake_rembg = SimpleNamespace(
            remove=MagicMock(return_value=result), new_session=MagicMock(),
        )
        with patch.dict(sys.modules, {"rembg": fake_rembg}):
            unchanged = remove_product_background(source)
            repaired = remove_product_background(
                source, preserve_interior=True,
            )
        self.assertEqual(unchanged.getpixel((50, 50))[3], 0)
        self.assertEqual(repaired.getpixel((50, 50)), (255, 255, 255, 255))

    def test_solid_repair_restores_faded_grille_connected_to_exterior(self):
        source = Image.new("RGB", (80, 100), "white")
        ImageDraw.Draw(source).rectangle((15, 10, 65, 90), fill="#333333")
        alpha = Image.new("L", source.size)
        draw = ImageDraw.Draw(alpha)
        draw.rectangle((15, 10, 65, 90), fill=255)
        # Unlike an enclosed hole, this faded patch reaches the lower edge.
        draw.rectangle((30, 50, 55, 90), fill=40)
        draw.rectangle((15, 10, 15, 90), fill=90)
        cutout = source.convert("RGBA")
        cutout.putalpha(alpha)
        repaired = restore_solid_interiors(source, cutout)
        self.assertEqual(repaired.getpixel((40, 75)), (51, 51, 51, 255))
        self.assertEqual(repaired.getpixel((15, 40))[3], 90)
        self.assertEqual(repaired.getpixel((0, 0))[3], 0)
        self.assertEqual(repaired.getpixel((40, 95))[3], 0)
        self.assertEqual(cutout.getpixel((40, 75))[3], 40)

    def test_solid_body_cutout_has_a_distinct_cache_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "product.png"
            Image.new("RGB", (100, 100), "white").save(source)
            stale = source.with_name("product_solid_cutout.png")
            transparent_product().save(stale)
            with patch(
                "src.imaging.product_cutout.remove_product_background",
                return_value=transparent_product(),
            ) as remove:
                normal = save_product_cutout(source)
                solid = save_product_cutout(source, preserve_interior=True)
            self.assertNotEqual(normal, solid)
            self.assertNotEqual(stale, solid)
            self.assertEqual(remove.call_count, 2)
            self.assertTrue(normal.exists())
            self.assertTrue(solid.exists())
