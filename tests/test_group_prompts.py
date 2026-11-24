# Verify short product-specific prompts and complete group coverage.

import unittest

from src.catalog.product_catalog import build_catalog_plan
from src.prompts.products import (
    build_group_image_prompt, build_group_image_prompts,
)


class GroupPromptTests(unittest.TestCase):
    def test_short_prompt_contains_only_the_supplied_product_type(self):
        prompt = build_group_image_prompt([
            "Viet-Tiep cast-iron padlock, 50mm",
        ])
        self.assertIn("Viet-Tiep cast-iron padlock, 50mm", prompt)
        self.assertNotIn("watch", prompt)
        self.assertNotIn("screen", prompt)
        self.assertNotIn("grid", prompt)
        self.assertLess(len(prompt), 500)
        self.assertNotIn("1.", prompt)

    def test_separate_requests_preserve_all_descriptions(self):
        descriptions = ["Phone {Pro}", "Blue tablet", "Black headphones"]
        prompts = build_group_image_prompts(descriptions)
        self.assertEqual(len(prompts), 3)
        for description, prompt in zip(descriptions, prompts):
            self.assertIn(description, prompt)
            self.assertIn("single", prompt)
            for other in set(descriptions) - {description}:
                self.assertNotIn(other, prompt)

    def test_empty_items_and_oversized_descriptions_fail(self):
        for descriptions in ([], [""], ["   "], ["x" * 4000]):
            with self.subTest(descriptions=descriptions):
                with self.assertRaises(ValueError):
                    build_group_image_prompts(descriptions)

    def test_group_shot_helper_preserves_variants_without_numbering(self):
        prompt = build_group_image_prompt(["Speaker black", "Speaker cream"])
        self.assertIn("Speaker black; Speaker cream", prompt)
        self.assertNotIn("1.", prompt)
        self.assertNotIn("2.", prompt)

    def test_no_product_is_omitted_from_a_group_larger_than_six(self):
        catalog = {str(i): {
            "tên sản phẩm": f"Phone {i}", "category_id": "27",
            "category_name": "Điện thoại", "quantity_sold": i,
        } for i in range(8)}
        plan = build_catalog_plan(list(catalog), catalog)
        category = plan["categories"][0]
        self.assertEqual(len(category["selected_products"]), 8)
        self.assertEqual(category["omitted_count"], 0)
        self.assertEqual(len(plan["requests"]), 8)
        self.assertEqual(len(category["request_keys"]), 8)
        for index, key in enumerate(category["request_keys"]):
            settings = category["request_settings"][key]
            self.assertEqual(settings["productcode"], str(7 - index))
            self.assertEqual(plan["requests"][key]["n"], 1)
