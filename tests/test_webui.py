import json
import unittest
from http.client import HTTPConnection
from urllib.parse import urlsplit

from akki.webui import WebUI


class WebUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui = WebUI(
            lambda text: {"ok": True, "message": f"echo {text}", "data": {}},
            host="127.0.0.1",
            port=0,
            status=lambda: {
                "version": "test",
                "profile": "sovereign",
                "model": "local",
            },
            tools=lambda: [{"name": "open_url"}],
        )
        self.url = self.ui.start()
        split = urlsplit(self.url)
        self.host = split.hostname or "127.0.0.1"
        self.port = split.port or 80

    def tearDown(self) -> None:
        self.ui.stop()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        connection = HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_index_is_served(self) -> None:
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"AKKI", body)

    def test_status_and_tools(self) -> None:
        status, body = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["version"], "test")
        status, body = self.request("GET", "/api/tools")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["tools"][0]["name"], "open_url")

    def test_chat_round_trip(self) -> None:
        body = json.dumps({"text": "hello"}).encode("utf-8")
        status, payload = self.request(
            "POST",
            "/api/chat",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["message"], "echo hello")

    def test_chat_rejects_empty_text(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/chat",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(payload)["ok"])


if __name__ == "__main__":
    unittest.main()
