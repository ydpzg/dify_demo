#!/usr/bin/env python3
"""Mock business API for importing into Dify as an OpenAPI tool.

All records and refunds are synthetic. This server never changes real business data.
"""

from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
ORDERS = {
    "order-1001": {"order_id": "order-1001", "status": "delivered", "total": 58.5, "currency": "USD"},
    "order-1002": {"order_id": "order-1002", "status": "processing", "total": 132.0, "currency": "USD"},
}


def load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


class BusinessHandler(BaseHTTPRequestHandler):
    server_version = "DifyBusinessDemo/1.0"

    def _send_json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = os.environ.get("DEMO_BUSINESS_API_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")

    def _read_json(self) -> dict | None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if size < 0 or size > 1_000_000:
            return None
        try:
            value = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"ok": True, "demo": True})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "orders":
            order = ORDERS.get(parts[1])
            if order:
                self._send_json(200, {"data": order, "demo": True})
            else:
                self._send_json(404, {"error": "order_not_found", "order_id": parts[1]})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/refunds":
            self._send_json(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        payload = self._read_json()
        if payload is None:
            self._send_json(400, {"error": "invalid_json"})
            return
        order_id = str(payload.get("order_id", ""))
        reason = str(payload.get("reason", "")).strip()
        order = ORDERS.get(order_id)
        try:
            amount = float(payload.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        if not order or not reason or amount <= 0 or amount > order["total"]:
            self._send_json(422, {"error": "invalid_refund_request"})
            return
        self._send_json(
            200,
            {
                "refund_id": "refund-demo-0001",
                "order_id": order_id,
                "amount": amount,
                "currency": order["currency"],
                "status": "SIMULATED",
                "message": "Demo only: no real refund was issued.",
            },
        )

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.client_address[0]} - {fmt % args}")


def main() -> None:
    load_dotenv()
    if not os.environ.get("DEMO_BUSINESS_API_TOKEN"):
        raise SystemExit("请先在 .env 设置 DEMO_BUSINESS_API_TOKEN")
    host = os.getenv("BUSINESS_API_HOST", "0.0.0.0")
    port = int(os.getenv("BUSINESS_API_PORT", "8088"))
    server = ThreadingHTTPServer((host, port), BusinessHandler)
    print(f"Mock business API listening on http://{host}:{port}")
    print("Synthetic orders only; POST /refunds simulates and never issues a real refund.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mock business API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
