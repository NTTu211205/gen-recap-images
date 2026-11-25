# Test category precedence and the grouped API-to-composition workflow.

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from src.catalog.product_catalog import build_catalog_plan
from src.catalog.product_groups import group_products, load_category_groups


class ProductGroupTests(unittest.TestCase):
    def test_vouchers_are_not_classified_as_physical_products(self):
        groups = group_products([
            "PMH Tablet iPad 500.000đ", "Máy tính bảng iPad 11",
            "Miếng dán iPad", "Dịch vụ giao hàng", "AirTime Mobi",
        ])
        self.assertEqual(groups["vouchers"], ["PMH Tablet iPad 500.000đ"])
        self.assertEqual(groups["phones"], ["Máy tính bảng iPad 11"])
        self.assertEqual(groups["accessories"], ["Miếng dán iPad"])
        with self.assertRaisesRegex(ValueError, "classification rules"):
            group_products(["Unknown product"])


class CategoryTaxonomyTests(unittest.TestCase):
    def test_taxonomy_covers_all_catalog_labels_once(self):
        root = Path(__file__).resolve().parent.parent
        catalog = json.loads(
            (root / "data/api_crawl_infor_new.json").read_text()
        )
        expected = {str(row["category_id"]).strip() for row in catalog}
        groups = load_category_groups()
        actual = set(groups) - {"__other__"}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 193)
        self.assertEqual(len({groups[key]["group_id"] for key in actual}), 9)

    def test_source_categories_share_one_recapped_group(self):
        catalog = {
            "phone": {"tên sản phẩm": "Phone A", "category_id": "27",
                      "category_name": "Điện thoại", "quantity_sold": 20},
            "tablet": {"tên sản phẩm": "Tablet A", "category_id": "30",
                       "category_name": "Máy tính bảng", "quantity_sold": 10},
        }
        plan = build_catalog_plan(list(catalog), catalog)
        self.assertEqual(len(plan["categories"]), 1)
        self.assertEqual(len(plan["requests"]), 1)
        group = plan["categories"][0]
        self.assertEqual(group["id"], "phones_tablets")
        self.assertEqual(group["name"], "Điện thoại & Máy tính bảng")
        self.assertEqual(
            [p["category_id"] for p in group["products"]], ["27", "30"],
        )
        self.assertEqual(
            [c["id"] for c in group["source_categories"]], ["27", "30"],
        )

    def test_service_label_is_not_sent_to_image_generation(self):
        plan = build_catalog_plan(["service"], {"service": {
            "tên sản phẩm": "Maintenance package", "category_id": "47",
            "category_name": "Dịch vụ vệ sinh, bảo dưỡng",
        }})
        self.assertEqual(plan["requests"], {})
        self.assertEqual(plan["excluded"][0]["reason"], "services")

    def test_unknown_category_uses_configured_other_group(self):
        plan = build_catalog_plan(["new"], {"new": {
            "tên sản phẩm": "New product", "category_id": "unmapped",
            "category_name": "New category",
        }})
        self.assertEqual(plan["categories"][0]["id"], "other")
        self.assertEqual(plan["categories"][0]["name"], "Sản phẩm khác")

    def test_invalid_group_and_duplicate_label_are_rejected(self):
        base = {
            "version": 2,
            "groups": [{
                "id": "other", "name": "Other", "generate_image": True,
            }],
        }
        cases = [
            [{"category_id": "27", "name": "Phone", "group_id": "missing"}],
            [{"category_id": "27", "name": "Phone", "group_id": "other"}] * 2,
        ]
        for labels in cases:
            with self.subTest(labels=labels):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "labels.yaml"
                    path.write_text(yaml.safe_dump({**base, "labels": labels}))
                    with self.assertRaises(ValueError):
                        load_category_groups(path)
