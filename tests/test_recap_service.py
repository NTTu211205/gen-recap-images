# Verify catalog preflight, capacity recovery and complete multi-page output.

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image

from src.core.config import Settings
from src.services.recap_service import ProductSelectionError, RecapService
from src.core.recap_config import RecapConfig


def service_for_groups(count, output_dir):
    catalog = {}
    groups = {"__other__": {
        "group_id": "other", "group_name": "Other", "generate_image": True,
    }}
    for index in range(count):
        code = f"{index:03d}"
        catalog[code] = {
            "tên sản phẩm": f"Product {index}", "category_id": str(index),
        }
        groups[str(index)] = {
            "group_id": f"group_{index}", "group_name": f"Group {index}",
            "generate_image": True,
        }
    return RecapService(
        RecapConfig(api_key="test"), catalog=catalog,
        category_groups=groups, output_dir=output_dir,
    )


class RecapServiceTests(unittest.TestCase):
    def test_startup_requires_all_background_variants(self):
        settings = Settings(_env_file=None, MWG_API_KEY="test")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-8.png").touch()
            with patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ):
                with self.assertRaisesRegex(
                    FileNotFoundError, "mwg-background-recap-1.png",
                ):
                    RecapService.from_settings(settings)

    def test_unknown_code_fails_before_any_mwg_calls(self):
        service = service_for_groups(1, Path("unused"))
        with patch("src.services.recap_service.post_json_with_curl") as post:
            with patch(
                "src.services.recap_service.generate_recap",
            ) as generate:
                with self.assertRaises(ProductSelectionError) as caught:
                    service.generate(["000", "999"])
        self.assertEqual(caught.exception.excluded, [{
            "productcode": "999", "reason": "catalog_not_found",
        }])
        post.assert_not_called()
        generate.assert_not_called()

    def test_timeout_releases_capacity_for_the_next_request(self):
        service = service_for_groups(1, Path("unused"))
        with patch.object(service, "_generate", side_effect=[
            requests.Timeout(), Path("final.png"),
        ]):
            with self.assertRaises(requests.Timeout):
                service.generate(["000"])
            self.assertEqual(service.generate(["000"]), Path("final.png"))

    def test_duplicate_codes_generate_one_product_and_return_one_page(self):
        service = service_for_groups(1, Path("unused"))
        with patch(
            "src.services.recap_service.QwenProductTranslator",
        ) as translator:
            translator.return_value.translate.side_effect = (
                lambda text: json.loads(text)["name"]
            )
            with patch(
                "src.services.recap_service.generate_recap",
                return_value=Path("1.png"),
            ) as generate:
                self.assertEqual(
                    service.generate(["000", "000"]), Path("1.png"),
                )
        plan = generate.call_args.args[1]
        self.assertEqual(len(plan["requests"]), 1)
        self.assertEqual(len(plan["categories"]), 1)
        translator.return_value.translate.assert_called_once()

    def test_ninth_group_is_included_in_one_combined_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "recap_01_final.png"
            second = root / "recap_02_final.png"
            Image.new("RGB", (30, 20), "red").save(first)
            Image.new("RGB", (30, 15), "blue").save(second)
            originals = [path.read_bytes() for path in (first, second)]
            service = service_for_groups(9, root)
            with patch(
                "src.services.recap_service.QwenProductTranslator",
            ) as qwen:
                qwen.return_value.translate.side_effect = (
                    lambda text: json.loads(text)["name"]
                )
                with patch(
                    "src.services.recap_service.generate_recap",
                    return_value=first,
                ):
                    result = service.generate([f"{i:03d}" for i in range(9)])
            with Image.open(result) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (30, 35))
                self.assertEqual(image.getpixel((15, 10)), (255, 0, 0))
                self.assertEqual(image.getpixel((15, 30)), (0, 0, 255))
            self.assertEqual(
                [path.read_bytes() for path in (first, second)], originals,
            )

    def test_missing_key_fails_startup_and_settings_hide_credentials(self):
        settings = Settings(_env_file=None, MWG_API_KEY="")
        with self.assertRaisesRegex(ValueError, "Missing MWG_API_KEY"):
            RecapService.from_settings(settings)
        settings = Settings(
            _env_file=None, MWG_API_KEY="test-secret",
            MWG_COOKIE="cookie-secret",
        )
        self.assertNotIn("test-secret", repr(settings))
        self.assertNotIn("cookie-secret", repr(settings))
