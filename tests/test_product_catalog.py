# Verify product-code identity, ranking and dynamic category placement.

import base64
import io
import tempfile
import json
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

import requests
from PIL import Image, ImageDraw

from src.catalog.product_catalog import (
    build_catalog_plan, resolve_and_rank,
)
from src.services.recap_pipeline import generate_recap
from src.imaging.recap_layout import category_layout


class ProductCatalogTests(unittest.TestCase):
    def test_speakers_preserve_solid_grilles_but_headphones_keep_open_gaps(
        self,
    ):
        catalog = {
            "001": {"tên sản phẩm": "Loa Marshall", "category_id": "132"},
            "002": {"tên sản phẩm": "Tai nghe Sony", "category_id": "133"},
        }
        plan = build_catalog_plan(list(catalog), catalog)
        settings = {
            option["productcode"]: option["preserve_interior"]
            for category in plan["categories"]
            for option in category["request_settings"].values()
        }
        self.assertEqual(settings, {"001": True, "002": False})

    def test_plan_preserves_and_deduplicates_codes(self):
        catalog = {
            "001": {
                "tên sản phẩm": "Phone A", "category_id": "27",
                "quantity_sold": 20,
            },
            "002": {
                "tên sản phẩm": "Phone B", "category_id": "27",
                "quantity_sold": 10,
            },
        }
        plan = build_catalog_plan(["001", "002", "001"], catalog)
        self.assertEqual(len(plan["requests"]), 2)
        self.assertEqual(len(plan["categories"][0]["selected_products"]), 2)

    def test_parallel_images_keep_group_identity_when_completed_out_of_order(
        self,
    ):
        plan = {
            "groups": {"phones": ["Phone"], "appliances": ["Fan"]},
            "requests": {
                "phones": {"prompt": "Phone"},
                "appliances": {"prompt": "Fan"},
            },
        }
        second_done = Event()

        def generate(prompt):
            image = Image.new("RGBA", (100, 100))
            color = "red" if prompt == "Phone" else "blue"
            ImageDraw.Draw(image).rectangle((25, 15, 75, 85), fill=color)
            data = io.BytesIO()
            image.save(data, format="PNG")
            if prompt == "Phone":
                self.assertTrue(second_done.wait(2))
            else:
                second_done.set()
            return {"data": [
                base64.b64encode(data.getvalue()).decode("ascii"),
            ]}

        client = MagicMock()
        client.generate_image.side_effect = generate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-2.png").touch()
            with patch("src.services.recap_pipeline.find_font"), patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ), patch("src.services.recap_pipeline.compose_recap") as compose:
                generate_recap(client, plan, root, image_workers=2)
            assets = compose.call_args.args[0]
            self.assertEqual(list(assets), ["phones", "appliances"])
            for key, color in (
                ("phones", (255, 0, 0, 255)),
                ("appliances", (0, 0, 255, 255)),
            ):
                with Image.open(assets[key]) as image:
                    self.assertEqual(image.getpixel((50, 50)), color)
        self.assertEqual(client.generate_image.call_count, 2)

    def test_lookup_uses_trimmed_code_and_keeps_leading_zeros(self):
        catalog = {"00123": {
            "tên sản phẩm": "Phone A", "category_id": "27",
            "category_name": "Điện thoại",
        }}
        ranked, excluded = resolve_and_rank([" 00123 "], catalog)
        self.assertFalse(excluded)
        self.assertEqual(ranked[0]["name"], "Phone A")
        self.assertEqual(ranked[0]["category_id"], "27")
        self.assertEqual(ranked[0]["productcode"], "00123")

    def test_rank_deduplicates_codes_and_keeps_all_group_products(self):
        catalog = {code: {
            "tên sản phẩm": f"Phone {code.upper()}",
            "category_id": "27", "category_name": "Điện thoại",
            "quantity_sold": {"a": 120, "b": 100, "c": 100, "d": 20}[code],
            "rating_vote": {"a": 4, "b": 5, "c": 4, "d": 5}[code],
        } for code in "abcd"}
        plan = build_catalog_plan(
            ["a", "a", "b", "c", "d"], catalog,
        )
        category = plan["categories"][0]
        self.assertEqual([
            product["productcode"] for product in category["selected_products"]
        ], ["a", "b", "c", "d"])
        self.assertEqual(category["omitted_count"], 0)
        descriptions = "\n".join(plan["groups"][category["key"]])
        self.assertIn("Phone D", descriptions)
        prompt = "\n".join(
            plan["requests"][key]["prompt"] for key in category["request_keys"]
        )
        self.assertIn("Điện thoại", prompt)
        self.assertEqual(len(plan["requests"]), 4)

    def test_layout_keeps_image_key_and_category_name_together(self):
        for count in range(1, 9):
            names = {
                f"id-{index}": f"Category {index}" for index in range(count)
            }
            layout = category_layout(names)
            self.assertEqual([item["key"] for item in layout], list(names))
            for item in layout:
                self.assertEqual(item["label"], names[item["key"]])
                left, top, right, bottom = item["slot"]
                self.assertGreater(right, left)
                self.assertGreater(bottom, top)
                self.assertLess(item["badge"][1], bottom)
                self.assertGreater(item["badge"][3], bottom)
        with self.assertRaises(ValueError):
            category_layout({})

    def test_unknown_code_is_reported_without_guessing_a_product(self):
        plan = build_catalog_plan(["unknown"], {})
        self.assertEqual(plan["requests"], {})
        self.assertEqual(plan["excluded"], [{
            "productcode": "unknown", "reason": "catalog_not_found",
        }])

    def test_catalog_popularity_orders_requested_codes(self):
        catalog = {
            "a": {"tên sản phẩm": "Phone A", "category_id": "27",
                  "category_name": "Điện thoại", "quantity_sold": "10"},
            "b": {"tên sản phẩm": "Phone B", "category_id": "27",
                  "category_name": "Điện thoại", "quantity_sold": "20"},
        }
        plan = build_catalog_plan(
            ["a", "b", "a"], catalog,
        )
        self.assertEqual([
            product["productcode"]
            for product in plan["categories"][0]["selected_products"]
        ], ["b", "a"])

    def test_new_catalog_category_needs_no_fixed_template_entry(self):
        catalog = {"new": {
            "tên sản phẩm": "Travel bag", "category_id": "new-category",
            "category_name": "Du lịch", "quantity_sold": 12,
        }}
        plan = build_catalog_plan(["new"], catalog, category_groups={
            "new-category": {
                "group_id": "new-category", "group_name": "Du lịch",
                "generate_image": True,
            },
        })
        self.assertEqual(plan["categories"][0]["name"], "Du lịch")
        self.assertEqual(plan["categories"][0]["id"], "new-category")

    def test_nine_groups_paginate_without_mismatching_assets(self):
        catalog = {str(index): {
            "tên sản phẩm": f"Product {index}", "category_id": str(index),
            "category_name": f"Category {index}", "quantity_sold": index,
        } for index in range(9)}
        category_groups = {str(index): {
            "group_id": str(index), "group_name": f"Category {index}",
            "generate_image": True,
        } for index in range(9)}
        plan = build_catalog_plan(
            list(catalog), catalog,
            category_groups=category_groups,
        )
        # Request order must not control label placement.
        plan["requests"] = dict(reversed(list(plan["requests"].items())))
        image_buffer = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(image_buffer, format="PNG")
        client = MagicMock()
        client.generate_image.return_value = {"data": [
            base64.b64encode(image_buffer.getvalue()).decode("ascii"),
        ]}
        with tempfile.TemporaryDirectory() as directory:
            for count in (1, 8):
                (Path(directory) / f"mwg-background-recap-{count}.png").touch()
            with patch("src.services.recap_pipeline.find_font"), patch(
                "src.imaging.background_templates.BACKGROUND_DIR",
                Path(directory),
            ), patch(
                "src.services.recap_pipeline.save_product_cutout",
                side_effect=lambda path, **options: path,
            ):
                with patch(
                    "src.services.recap_pipeline.compose_recap",
                ) as compose:
                    compose.side_effect = lambda a, g, p, **kwargs: p
                    generate_recap(client, plan, Path(directory))
                    self.assertEqual(compose.call_count, 2)
                    all_keys = []
                    for call in compose.call_args_list:
                        assets = call.args[0]
                        names = call.kwargs["category_names"]
                        icons = call.kwargs["category_icons"]
                        self.assertEqual(
                            call.kwargs["background_path"].name,
                            f"mwg-background-recap-{len(names)}.png",
                        )
                        self.assertEqual(list(assets), list(names))
                        for category in plan["categories"]:
                            if category["key"] in names:
                                self.assertEqual(
                                    icons[category["key"]], category["id"],
                                )
                        for key, path in assets.items():
                            self.assertTrue(path.name.startswith(key))
                        all_keys.extend(names)
                    self.assertEqual(all_keys, [
                        category["key"] for category in plan["categories"]
                    ])

    def test_missing_background_stops_before_image_api_call(self):
        plan = {
            "requests": {"category": {"prompt": "Phone"}},
            "groups": {"phones": ["Phone"]},
        }
        client = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "src.imaging.background_templates.BACKGROUND_DIR",
                Path(directory),
            ):
                with self.assertRaises(FileNotFoundError):
                    generate_recap(client, plan, Path(directory))
        client.generate_image.assert_not_called()

    def test_timeout_preserves_completed_group_checkpoints(self):
        plan = {
            "groups": {"phones": ["Phone"], "appliances": ["Fan"]},
            "requests": {
                "phones": {"prompt": "Phone"},
                "appliances": {"prompt": "Fan"},
            },
        }
        data = io.BytesIO()
        image = Image.new("RGBA", (100, 100))
        ImageDraw.Draw(image).rectangle((25, 15, 75, 85), fill="red")
        image.save(data, format="PNG")
        client = MagicMock()
        client.generate_image.side_effect = [
            {"data": [base64.b64encode(data.getvalue()).decode("ascii")]},
            requests.Timeout(),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-2.png").touch()
            with patch("src.services.recap_pipeline.find_font"), patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ), patch("src.services.recap_pipeline.compose_recap") as compose:
                with self.assertRaises(requests.Timeout):
                    generate_recap(client, plan, root)
            compose.assert_not_called()
            run_dir = next(root.glob("recap_*"))
            for filename in ("request_assets.json", "assets.json"):
                saved = json.loads((run_dir / filename).read_text())
                self.assertEqual(list(saved), ["phones"])
                self.assertTrue((run_dir / saved["phones"]).is_file())
            self.assertEqual(
                json.loads((run_dir / "plan.json").read_text()), plan,
            )
        self.assertEqual(client.generate_image.call_count, 2)

    def test_parallel_failure_keeps_other_inflight_image_without_new_calls(
        self,
    ):
        plan = {
            "groups": {key: [key] for key in ("a", "b", "c")},
            "requests": {
                key: {"prompt": key} for key in ("a", "b", "c")
            },
        }
        second_started = Event()
        data = io.BytesIO()
        Image.new("RGB", (10, 10), "blue").save(data, format="PNG")

        def generate(prompt):
            if prompt == "a":
                self.assertTrue(second_started.wait(2))
                raise requests.Timeout()
            second_started.set()
            return {"data": [
                base64.b64encode(data.getvalue()).decode("ascii"),
            ]}

        client = MagicMock()
        client.generate_image.side_effect = generate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-3.png").touch()
            with patch("src.services.recap_pipeline.find_font"), patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ), patch("src.services.recap_pipeline.compose_recap") as compose:
                with self.assertRaises(requests.Timeout):
                    generate_recap(client, plan, root, image_workers=2)
            compose.assert_not_called()
            run_dir = next(root.glob("recap_*"))
            saved = [
                p for p in run_dir.glob("b_*.png") if "_cutout" not in p.name
            ]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_bytes(), data.getvalue())
        self.assertEqual(client.generate_image.call_count, 2)

    def test_missing_last_page_template_stops_before_any_image_calls(self):
        plan = {
            "categories": [{"key": str(i)} for i in range(9)],
            "requests": {"category": {"prompt": "Phone"}},
        }
        client = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-8.png").touch()
            with patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ):
                with self.assertRaisesRegex(
                    FileNotFoundError, "mwg-background-recap-1.png",
                ):
                    generate_recap(client, plan, root)
        client.generate_image.assert_not_called()

    def test_product_requests_are_merged_back_into_one_labeled_group(self):
        catalog = {str(i): {
            "tên sản phẩm": f"Product {i}", "category_id": "27",
            "category_name": "Điện thoại",
        } for i in range(10)}
        plan = build_catalog_plan(list(catalog), catalog)
        category = plan["categories"][0]
        self.assertGreater(len(category["request_keys"]), 1)
        image = Image.new("RGBA", (100, 100))
        ImageDraw.Draw(image).rectangle((25, 15, 75, 85), fill="red")
        data = io.BytesIO()
        image.save(data, format="PNG")
        client = MagicMock()
        client.generate_image.return_value = {"data": [
            base64.b64encode(data.getvalue()).decode("ascii"),
        ]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mwg-background-recap-1.png").touch()
            with patch("src.services.recap_pipeline.find_font"), patch(
                "src.imaging.background_templates.BACKGROUND_DIR", root,
            ), patch("src.services.recap_pipeline.compose_recap") as compose:
                compose.side_effect = lambda a, g, p, **kwargs: p
                generate_recap(client, plan, root)
            self.assertEqual(
                client.generate_image.call_count,
                len(category["request_keys"]),
            )
            self.assertEqual(
                list(compose.call_args.args[0]), [category["key"]],
            )
            self.assertEqual(
                compose.call_args.kwargs["background_path"].name,
                "mwg-background-recap-1.png",
            )
            combined_path = compose.call_args.args[0][category["key"]]
            with Image.open(combined_path) as combined:
                self.assertEqual(combined.mode, "RGBA")
                self.assertEqual(combined.getpixel((0, 0))[3], 0)
            self.assertEqual(len(category["selected_products"]), 10)
            self.assertEqual(category["omitted_count"], 0)
