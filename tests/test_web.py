import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from akki.config import Config
from akki.tools.web import extract_web_text, read_page, read_url


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class WebToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "page.html").write_text(
            "<html><head><title>Title</title><script>bad()</script></head>"
            "<body><h1>Hello</h1><p>World</p></body></html>",
            encoding="utf-8",
        )
        handler = partial(QuietHandler, directory=str(root))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = int(self.server.server_address[1])

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def test_extract_web_text_skips_scripts(self) -> None:
        text = extract_web_text(
            "<html><head><script>bad()</script></head><body>Hello <b>world</b></body></html>"
        )
        self.assertEqual(text, "Hello world")

    def test_read_page_and_read_url(self) -> None:
        url = f"http://127.0.0.1:{self.port}/page.html"
        target, text = read_page(url)
        self.assertEqual(target, url)
        self.assertIn("Hello World", text)
        self.assertNotIn("bad", text)
        result = read_url(url, config=Config.default())
        self.assertTrue(result.ok)
        self.assertIn("Hello World", result.data["text"])

    def test_read_url_rejects_invalid_scheme(self) -> None:
        result = read_url("file:///etc/passwd", config=Config.default())
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
