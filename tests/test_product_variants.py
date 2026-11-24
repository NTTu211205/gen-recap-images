# Verify complete group membership and duplicate/variant handling.

import unittest

from src.catalog.product_catalog import build_catalog_plan


def speaker(color, *, name="Loa Marshall Emberton III", sold=0):
    return {
        "tên sản phẩm": name, "màu sắc": color, "brand": "Marshall",
        "category_id": "133", "category_name": "Tai nghe",
        "quantity_sold": sold,
    }


class ProductVariantTests(unittest.TestCase):
    def test_duplicate_variant_is_rendered_once(self):
        catalog = {
            "a": speaker("Đen", sold=20),
            "b": speaker(
                "đen", name="  LOA   Marshall Emberton III ", sold=10,
            ),
        }
        plan = build_catalog_plan(["a", "a", "b"], catalog)
        group = plan["categories"][0]
        self.assertEqual(len(group["products"]), 1)
        self.assertEqual(
            group["selected_products"][0]["productcodes"], ["a", "b"],
        )
        self.assertEqual(plan["duplicates"], [{
            "productcode": "b", "duplicate_of": "a",
        }])
        self.assertEqual(len(plan["groups"][group["key"]]), 1)

    def test_different_colors_are_preserved(self):
        plan = build_catalog_plan(["black", "cream"], {
            "black": speaker("Đen", sold=20), "cream": speaker("Kem", sold=10),
        })
        self.assertEqual(plan["duplicates"], [])
        group = plan["categories"][0]
        self.assertEqual(len(group["selected_products"]), 2)
        self.assertEqual(group["selected_products"][0]["color"], "Đen")
        self.assertEqual(group["selected_products"][1]["color"], "Kem")
        names = "\n".join(plan["groups"][group["key"]])
        self.assertIn("Loa Marshall Emberton III", names)
        prompt = "\n".join(
            plan["requests"][key]["prompt"] for key in group["request_keys"]
        )
        self.assertIn("Tai nghe", prompt)

    def test_different_capacities_are_not_merged(self):
        catalog = {str(size): {
            "tên sản phẩm": f"Phone {size}GB", "category_id": "27",
            "category_name": "Điện thoại", "màu sắc": "Black",
        } for size in (128, 256)}
        plan = build_catalog_plan(list(catalog), catalog)
        self.assertEqual(len(plan["categories"][0]["products"]), 2)
        self.assertEqual(plan["duplicates"], [])
        self.assertEqual(len(plan["categories"][0]["products"]), 2)
        self.assertEqual(plan["duplicates"], [])
