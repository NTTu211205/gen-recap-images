# Regression tests that never call the image generation API.

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.clients.image_generation import CurlImageClient, MWGImageClient
from src.core.recap_config import RecapConfig
from src.imaging.image_files import decode_image, save_image, save_images


class ShoppingRecapTests(unittest.TestCase):

    def test_config_requires_key_and_hides_credentials(self):
        with self.assertRaises(ValueError):
            RecapConfig(api_key=" ")
        config = RecapConfig(api_key="secret-key", cookie="secret-cookie")
        self.assertNotIn("secret", repr(config))

    def test_client_payload_and_http_errors(self):
        session = MagicMock()
        response = session.post.return_value.__enter__.return_value
        response.json.return_value = {"data": []}
        client = MWGImageClient(RecapConfig(api_key="test-key"), session)
        self.assertEqual(client.generate_image("prompt"), {"data": []})
        arguments = session.post.call_args.kwargs
        self.assertEqual(arguments["headers"]["apikey"], "test-key")
        self.assertEqual(arguments["json"], {
            "prompt": "prompt",
            "images": [],
            "size": "512x512",
            "n": 1,
            "steps": 8,
            "cfg": 1.0,
        })
        self.assertEqual(arguments["timeout"], (15, 300))
        response.raise_for_status.side_effect = requests.HTTPError()
        with self.assertRaises(requests.HTTPError):
            client.generate_image("prompt")
        response.raise_for_status.side_effect = None
        response.json.return_value = []
        with self.assertRaises(ValueError):
            client.generate_image("prompt")

    def test_curl_sends_utf8_payload_without_credentials_in_arguments(self):
        def fake_run(command, **kwargs):
            self.assertNotIn("secret-key", " ".join(command))
            self.assertIn("secret-key", kwargs["input"])
            payload_path = command[command.index("--data-binary") + 1][1:]
            self.assertIn("Điện thoại", Path(payload_path).read_text())
            response_path = command[command.index("--output") + 1]
            Path(response_path).write_text('{"data": []}')
            return MagicMock(returncode=0, stdout="HTTP 200")

        client = CurlImageClient(RecapConfig(api_key="secret-key"))
        with patch(
            "src.clients.mwg_http.subprocess.run", side_effect=fake_run,
        ):
            self.assertEqual(client.generate_image("Điện thoại"), {"data": []})

    def test_curl_timeout_does_not_retry(self):
        client = CurlImageClient(RecapConfig(api_key="test-key"))
        with patch("src.clients.mwg_http.subprocess.run") as run:
            run.return_value = MagicMock(returncode=28, stdout="HTTP 000")
            with self.assertRaises(requests.Timeout):
                client.generate_image("prompt")
            run.assert_called_once()

    def test_transports_share_payload_and_validation(self):
        config = RecapConfig(
            api_key="test-key", model="custom-model",
            image_size="512x512",
        )
        session = MagicMock()
        response = session.post.return_value.__enter__.return_value
        response.json.return_value = {"data": []}
        clients = (MWGImageClient(config, session), CurlImageClient(config))
        with patch(
            "src.clients.image_generation.post_json_with_curl",
            return_value={"data": []},
        ) as post:
            for client in clients:
                for prompt in ("", "x" * 4001):
                    with self.assertRaisesRegex(ValueError, "1-4000"):
                        client.generate_image(prompt)
            session.post.assert_not_called()
            post.assert_not_called()
            for client in clients:
                client.generate_image("Điện thoại")
            self.assertEqual(
                session.post.call_args.kwargs["json"], post.call_args.args[1],
            )
            payload = post.call_args.args[1]
            self.assertEqual(payload["prompt"], "Điện thoại")
            self.assertEqual(payload["size"], "512x512")
            self.assertEqual(payload["steps"], 8)
            self.assertEqual(payload["cfg"], 1.0)
            self.assertEqual(payload["images"], [])

    def test_client_timings_logging(self):
        session = MagicMock()
        response = session.post.return_value.__enter__.return_value
        response.json.return_value = {
            "data": [],
            "timings": {"generate_s": 9.0},
        }
        client = MWGImageClient(
            RecapConfig(api_key="test-key"), session,
        )
        with self.assertLogs(
            "src.clients.image_generation", level="INFO",
        ) as logs:
            client.generate_image("prompt")
        self.assertTrue(any("generate_s: 9.00s" in log for log in logs.output))

    def test_qwen_edit_image_contract(self):
        from src.prompts.products import build_edit_image_prompt
        prompt = build_edit_image_prompt("SmartWatch")
        self.assertIn("SmartWatch", prompt)
        self.assertNotIn("{product_type}", prompt)
        session = MagicMock()
        response = session.post.return_value.__enter__.return_value
        response.json.return_value = {"data": []}
        config = RecapConfig(api_key="test-key")
        client = MWGImageClient(config, session)
        image_url = (
            "https://cdn.tgdd.vn/2026/10/timerseo/366152-600x600-8.jpg"
        )
        client.generate_image(prompt, images=[image_url])
        arguments = session.post.call_args.kwargs
        self.assertEqual(
            config.api_url,
            "https://ai.itmwg.vn/ai-mwg/qwen-edit-image/v1/images/edits",
        )
        self.assertEqual(arguments["json"], {
            "prompt": prompt,
            "images": [image_url],
            "size": "512x512",
            "n": 1,
            "steps": 8,
            "cfg": 1.0,
        })

    def test_client_validates_prompt_length_before_http_request(self):
        session = MagicMock()
        client = MWGImageClient(RecapConfig(api_key="test-key"), session)
        for prompt in ("", "x" * 4001):
            with self.subTest(length=len(prompt)):
                with self.assertRaisesRegex(ValueError, "1-4000"):
                    client.generate_image(prompt)
        session.post.assert_not_called()
        response = session.post.return_value.__enter__.return_value
        response.json.return_value = {"data": []}
        for prompt in ("x", "x" * 4000):
            client.generate_image(prompt)
        self.assertEqual(session.post.call_count, 2)

    def test_saves_supported_formats_and_data_uri(self):
        signatures = {
            ".png": b"\x89PNG\r\n\x1a\n",
            ".jpg": b"\xff\xd8\xff",
            ".webp": b"RIFF\x00\x00\x00\x00WEBP",
        }
        with tempfile.TemporaryDirectory() as directory:
            for extension, content in signatures.items():
                with self.subTest(extension=extension):
                    encoded = base64.b64encode(content).decode("ascii")
                    response = {"data": [{"b64_json": encoded}]}
                    path = save_image(response, output_dir=Path(directory))
                    self.assertEqual(path.suffix, extension)
                    self.assertEqual(path.read_bytes(), content)
                    response["data"][0]["b64_json"] = (
                        f"data:image/test;base64,{encoded}"
                    )
                    self.assertEqual(decode_image(response), content)

    def test_saves_all_images_and_preserves_previous_batches(self):
        content = b"\x89PNG\r\n\x1a\n"
        encoded = base64.b64encode(content).decode("ascii")
        response = {"data": [{"b64_json": encoded}, encoded]}
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            first = save_images(response, output_dir=output_dir)
            second = save_images(response, output_dir=output_dir)
            self.assertEqual(len(set(first + second)), 4)
            self.assertEqual(len(list(output_dir.iterdir())), 4)
            for path in first + second:
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(path.suffix, ".png")

    def test_save_images_rejects_empty_data(self):
        for response in ({}, {"data": []}, {"data": "invalid"}):
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    save_images(response)

    def test_rejects_malformed_image_responses(self):
        responses = [
            {}, {"data": []}, {"data": [None]},
            {"data": [{"b64_json": 123}]},
            {"data": [{"b64_json": "data:broken"}]},
            {"data": [{"b64_json": "!!!"}]},
        ]
        for response in responses:
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    decode_image(response)
        with self.assertRaisesRegex(ValueError, "Unsupported image format"):
            save_image({"data": [{"b64_json": "aGVsbG8="}]})


if __name__ == "__main__":
    unittest.main()
