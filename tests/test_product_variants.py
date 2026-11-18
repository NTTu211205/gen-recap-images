# Verify complete group membership and duplicate/variant handling.

import json
import unittest
from unittest.mock import MagicMock

from src.catalog.product_catalog import build_catalog_plan


def speaker(color, *, name="Loa Marshall Emberton III", sold=0):
    return {
        "tên sản phẩm": name, "màu sắc": color, "brand": "Marshall",
        "category_id": "133", "category_name": "Tai nghe",
        "quantity_sold": sold,
    }


class ProductVariantTests(unittest.TestCase):
    def test_duplicate_variant_is_translated_and_rendered_once(self):
        catalog = {
            "a": speaker("Đen", sold=20),
            "b": speaker(
                "đen", name="  LOA   Marshall Emberton III ", sold=10,
            ),
        }
        translator = MagicMock(return_value="Marshall Emberton III, black")
        plan = build_catalog_plan(
            ["a", "a", "b"], catalog, translate_product=translator,
        )
        group = plan["categories"][0]
        self.assertEqual(len(group["products"]), 1)
        self.assertEqual(
            group["selected_products"][0]["productcodes"], ["a", "b"],
        )
        self.assertEqual(plan["duplicates"], [{
            "productcode": "b", "duplicate_of": "a",
        }])
        translator.assert_called_once()
        self.assertEqual(len(plan["groups"][group["key"]]), 1)

    def test_different_colors_are_preserved_and_sent_for_translation(self):
        translator = MagicMock(side_effect=[
            "Marshall Emberton III speaker, black",
            "Marshall Emberton III speaker, cream",
        ])
        plan = build_catalog_plan(["black", "cream"], {
            "black": speaker("Đen", sold=20), "cream": speaker("Kem", sold=10),
        }, translate_product=translator)
        self.assertEqual(plan["duplicates"], [])
        group = plan["categories"][0]
        self.assertEqual(len(group["selected_products"]), 2)
        self.assertEqual(
            json.loads(translator.call_args_list[0].args[0])["color"], "Đen",
        )
        self.assertEqual(
            json.loads(translator.call_args_list[1].args[0])["color"], "Kem",
        )
        prompt = "\n".join(
            plan["requests"][key]["prompt"] for key in group["request_keys"]
        )
        self.assertIn("Marshall Emberton III speaker, black", prompt)
        self.assertIn("Marshall Emberton III speaker, cream", prompt)

    def test_translation_must_not_erase_variant_differences(self):
        with self.assertRaisesRegex(ValueError, "duplicate descriptions"):
            build_catalog_plan(["black", "cream"], {
                "black": speaker("Đen"), "cream": speaker("Kem"),
            }, translate_product=lambda name: "Marshall Emberton III speaker")

    def test_different_capacities_are_not_merged(self):
        catalog = {str(size): {
            "tên sản phẩm": f"Phone {size}GB", "category_id": "27",
            "category_name": "Điện thoại", "màu sắc": "Black",
        } for size in (128, 256)}
        plan = build_catalog_plan(
            list(catalog), catalog,
            translate_product=lambda text: json.loads(text)["name"],
        )
        self.assertEqual(len(plan["categories"][0]["products"]), 2)
        self.assertEqual(plan["duplicates"], [])
