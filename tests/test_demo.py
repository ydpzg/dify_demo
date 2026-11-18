from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import business_api
from dify_demo import build_parser, parse_json_object


class DemoCliTests(unittest.TestCase):
    def test_agent_command_parses_streaming_inputs(self) -> None:
        args = build_parser().parse_args(["agent", "look up order-1001", "--user", "customer-1"])
        self.assertEqual(args.command, "agent")
        self.assertEqual(args.query, "look up order-1001")
        self.assertEqual(args.user, "customer-1")

    def test_json_option_must_be_object(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须是 JSON 对象"):
            parse_json_object("[]", "--inputs")


class MockBusinessApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.token_patch = patch.dict(os.environ, {"DEMO_BUSINESS_API_TOKEN": "test-token"})
        cls.token_patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), business_api.BusinessHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.token_patch.stop()

    def test_order_lookup_requires_token_and_returns_synthetic_data(self) -> None:
        request = Request(
            f"{self.base_url}/orders/order-1001",
            headers={"Authorization": "Bearer test-token"},
        )
        with urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        self.assertTrue(result["demo"])
        self.assertEqual(result["data"]["status"], "delivered")

    def test_refund_is_simulated(self) -> None:
        body = json.dumps(
            {"order_id": "order-1001", "amount": 10, "reason": "damaged"}
        ).encode()
        request = Request(
            f"{self.base_url}/refunds",
            data=body,
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            result = json.loads(response.read())
        self.assertEqual(result["status"], "SIMULATED")
        self.assertIn("no real refund", result["message"].lower())

    def test_order_lookup_rejects_missing_token(self) -> None:
        request = Request(f"{self.base_url}/orders/order-1001")
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
