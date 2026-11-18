# Verify Qwen translation contracts and translation-before-image ordering.

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.catalog.product_catalog import build_catalog_plan
from src.clients.product_translation import QWEN_API_URL, QwenProductTranslator
from src.cli.shopping_recap import main
from src.core.recap_config import RecapConfig


def chat_response(text, finish_reason="stop"):
    return {"choices": [{
        "message": {"role": "assistant", "content": text},
        "finish_reason": finish_reason,
    }]}


class ProductTranslationTests(unittest.TestCase):
    def test_payload_and_cache_preserve_the_original_name(self):
        source = "OPPO A6x 4+128GB Tím"
        english = "OPPO A6x smartphone, 4GB RAM, 128GB storage, purple"
        post = MagicMock(return_value=chat_response(english))
        translator = QwenProductTranslator(post)
        self.assertEqual(translator.translate(source), english)
        self.assertEqual(translator.translate(source), english)
        post.assert_called_once()
        payload = post.call_args.args[0]
        self.assertEqual(payload["model"], "MWG")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertEqual(payload["messages"][1], {
            "role": "user", "content": source,
        })

    def test_invalid_and_truncated_responses_are_not_cached(self):
        responses = [
            {}, {"choices": []}, {"choices": [None]},
            {"choices": [{"message": None}]},
            chat_response(""), chat_response("one\ntwo"),
            chat_response("x" * 1001), chat_response("incomplete", "length"),
        ]
        for response in responses:
            with self.subTest(response=response):
                translator = QwenProductTranslator(
                    MagicMock(return_value=response),
                )
                with self.assertRaises(ValueError):
                    translator.translate("Sản phẩm")
                self.assertEqual(translator.cache, {})

    def test_translates_all_products_and_keeps_group_labels(self):
        catalog = {str(index): {
            "tên sản phẩm": f"Sản phẩm {index}", "category_id": "new",
            "category_name": "Danh mục mới", "quantity_sold": index,
        } for index in range(5)}
        post = MagicMock(side_effect=[
            chat_response(f"Product {index}") for index in (4, 3, 2, 1, 0)
        ])
        translator = QwenProductTranslator(post)
        plan = build_catalog_plan(
            list(catalog), catalog,
            translate_product=translator.translate,
            category_groups={"new": {
                "group_id": "new", "group_name": "Danh mục mới",
                "generate_image": True,
            }},
        )
        self.assertEqual(post.call_count, 5)
        category = plan["categories"][0]
        self.assertEqual(category["name"], "Danh mục mới")
        self.assertEqual(
            category["selected_products"][0]["name"], "Sản phẩm 4",
        )
        self.assertEqual(plan["groups"][category["key"]], [
            "Product 4", "Product 3", "Product 2", "Product 1", "Product 0",
        ])
        self.assertEqual(plan["translation_needed"], [])
        self.assertEqual(category["omitted_count"], 0)

    def test_failed_translation_stops_plan_building(self):
        translator = QwenProductTranslator(
            MagicMock(side_effect=requests.HTTPError()),
        )
        with self.assertRaises(requests.HTTPError):
            build_catalog_plan(["new"], {"new": {
                "tên sản phẩm": "Sản phẩm mới", "category_id": "new",
                "category_name": "Danh mục mới",
            }}, translate_product=translator.translate)

    def test_translated_export_calls_qwen_without_generating_images(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            output_path = Path(directory) / "plan.json"
            catalog_path.write_text(json.dumps([{
                "productcode": "001", "tên sản phẩm": "Sản phẩm mới",
                "category_id": "new", "category_name": "Danh mục mới",
            }]))
            args = [
                "recap", "--productcodes", "001", "--catalog",
                str(catalog_path), "--export-plan", str(output_path),
                "--translate-products",
            ]
            with patch("sys.argv", args), patch(
                "src.cli.shopping_recap.RecapConfig.from_environment",
                return_value=RecapConfig(api_key="test-key"),
            ), patch(
                "src.cli.shopping_recap.post_json_with_curl",
                return_value=chat_response("New product"),
            ) as post, patch(
                "src.cli.shopping_recap.generate_recap",
            ) as generate:
                with patch(
                    "src.cli.shopping_recap.logging.basicConfig",
                ), patch(
                    "builtins.print",
                ):
                    main()
            self.assertEqual(post.call_args.args[0], QWEN_API_URL)
            self.assertEqual(post.call_args.kwargs["api_key"], "test-key")
            generate.assert_not_called()
            plan = json.loads(output_path.read_text())
            self.assertEqual(list(plan["groups"].values()), [["New product"]])

    def test_plain_plan_export_does_not_call_either_api(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "catalog.json"
            output_path = Path(directory) / "plan.json"
            catalog_path.write_text(json.dumps([{
                "productcode": "001", "tên sản phẩm": "Phone A",
                "category_id": "27", "category_name": "Điện thoại",
            }]))
            args = [
                "recap", "--productcodes", "001", "--catalog",
                str(catalog_path), "--export-plan", str(output_path),
            ]
            with patch("sys.argv", args), patch(
                "src.cli.shopping_recap.post_json_with_curl",
            ) as post, patch(
                "src.cli.shopping_recap.generate_recap",
            ) as generate, patch(
                "src.cli.shopping_recap.logging.basicConfig",
            ), patch("builtins.print"):
                main()
            post.assert_not_called()
            generate.assert_not_called()
            self.assertTrue(output_path.is_file())
            plan = json.loads(output_path.read_text())
            self.assertEqual(plan["requests"], {})
            self.assertEqual(plan["groups"], {})
            self.assertEqual(plan["translation_needed"], [{
                "productcode": "001", "name": "Phone A",
            }])
            category = plan["categories"][0]
            self.assertEqual(category["translation_status"], "pending")
            self.assertIsNone(
                category["selected_products"][0]["description_en"],
            )

    def test_draft_keeps_all_products_and_cannot_generate_images(self):
        from src.services.recap_pipeline import generate_recap

        catalog = {str(index): {
            "tên sản phẩm": f"Sản phẩm {index}", "category_id": "new",
            "category_name": "Danh mục mới", "quantity_sold": index,
        } for index in range(5)}
        plan = build_catalog_plan(list(catalog), catalog)
        selected = plan["categories"][0]["selected_products"]
        self.assertEqual(
            [p["productcode"] for p in selected], ["4", "3", "2", "1", "0"],
        )
        self.assertEqual(len(plan["translation_needed"]), 5)
        client = MagicMock()
        with self.assertRaisesRegex(ValueError, "Qwen translation"):
            generate_recap(client, plan, Path("unused"))
        client.generate_image.assert_not_called()

    def test_context_includes_source_category_brand_and_color(self):
        post = MagicMock(return_value=chat_response(
            "Marshall Emberton III Bluetooth speaker, cream",
        ))
        plan = build_catalog_plan(["speaker"], {"speaker": {
            "tên sản phẩm": "Loa Marshall Emberton III", "category_id": "132",
            "category_name": "Loa", "brand": "Marshall", "màu sắc": "Kem",
        }}, translate_product=QwenProductTranslator(post).translate)
        context = json.loads(post.call_args.args[0]["messages"][1]["content"])
        self.assertEqual(context["category"], "Loa")
        self.assertEqual(context["brand"], "Marshall")
        self.assertEqual(context["color"], "Kem")
        self.assertIn("cream", next(iter(plan["requests"].values()))["prompt"])

    def test_untranslated_color_and_material_are_not_cached(self):
        cases = [
            ({"name": "Loa", "category": "Loa", "color": "Kem"},
             "Marshall speaker Kem"),
            ({"name": "Ổ khóa gang 50 mm", "category": "Ổ Khoá", "color": ""},
             "Viet-Tiep 50mm Gang Lock"),
        ]
        for source, translated in cases:
            with self.subTest(source=source):
                translator = QwenProductTranslator(
                    MagicMock(return_value=chat_response(translated)),
                )
                with self.assertRaises(ValueError):
                    translator.translate(
                        json.dumps(source, ensure_ascii=False),
                    )
                self.assertEqual(translator.cache, {})

    def test_complete_eight_group_recap_uses_one_page(self):
        from src.imaging.recap_layout import GROUPS_PER_PAGE, category_layout

        self.assertEqual(GROUPS_PER_PAGE, 8)
        layout = category_layout({str(i): f"Group {i}" for i in range(8)})
        self.assertEqual(len(layout), 8)
        self.assertEqual(len({item["slot"] for item in layout}), 8)

    def test_missing_model_identifier_is_retained_from_source_name(self):
        source = json.dumps({
            "name": "Máy giặt Casper Inverter 10.5 kg WF-D105VGR1",
            "category": "Máy giặt", "color": "", "brand": "Casper",
        }, ensure_ascii=False)
        translator = QwenProductTranslator(MagicMock(
            return_value=chat_response(
                "Casper Inverter 10.5 kg washing machine",
            ),
        ))
        result = translator.translate(source)
        self.assertIn("WF-D105VGR1", result)
        self.assertEqual(translator.cache[source], result)

    def test_present_model_identifier_is_not_repeated(self):
        source = json.dumps({"name": "Bếp BlueStone ICB-6833 4000W"})
        description = "BlueStone ICB-6833 4000W dual-zone induction cooktop"
        translator = QwenProductTranslator(
            MagicMock(return_value=chat_response(description)),
        )
        self.assertEqual(translator.translate(source), description)
