import unittest

from akki.config import Config
from akki.router import route


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Config.default()

    def test_open_application(self) -> None:
        request = route("Open VS Code", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "launch_app")
        self.assertEqual(request.args["alias"].lower(), "vs code")

    def test_open_known_site(self) -> None:
        request = route("Open YouTube", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "open_url")
        self.assertIn("youtube", request.args["url"])

    def test_open_url(self) -> None:
        request = route("open https://example.com/docs", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "open_url")

    def test_web_search(self) -> None:
        request = route("Search Python decorators", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "web_search")
        self.assertEqual(request.args["query"], "Python decorators")

    def test_find_files_strips_project_suffix(self) -> None:
        request = route("Find my Finora project", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "find_files")
        self.assertEqual(request.args["query"].lower(), "finora")

    def test_open_in_application(self) -> None:
        request = route("Open my Finora project in VS Code", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "open_in_app")
        self.assertEqual(request.args["alias"], "VS Code")
        self.assertEqual(request.args["target"], "Finora project")

    def test_screenshot(self) -> None:
        self.assertEqual(route("Take a screenshot", self.config).tool, "screenshot")
        self.assertEqual(route("screenshot", self.config).tool, "screenshot")

    def test_volume(self) -> None:
        request = route("Increase the volume", self.config)
        self.assertEqual(request.tool, "volume")
        self.assertEqual(request.args["direction"], "up")
        self.assertEqual(request.args["steps"], 2)

        request = route("decrease volume by 4", self.config)
        self.assertEqual(request.args["direction"], "down")
        self.assertEqual(request.args["steps"], 4)

        self.assertEqual(route("mute", self.config).args["direction"], "mute")

    def test_go_to_site(self) -> None:
        request = route("go to youtube", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "open_url")

    def test_path_open(self) -> None:
        request = route(r"open C:\Users\ankit\Desktop", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "open_path")

    def test_read_url(self) -> None:
        request = route("read https://example.com/docs", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "read_url")

    def test_windows_tools(self) -> None:
        self.assertEqual(route("lock the computer", self.config).tool, "lock_screen")
        self.assertEqual(route("clipboard", self.config).tool, "clipboard_read")
        request = route("clipboard write hello world", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "clipboard_write")
        self.assertEqual(request.args["text"], "hello world")

    def test_unknown_request(self) -> None:
        self.assertIsNone(route("what is the weather tomorrow", self.config))

    def test_empty_request(self) -> None:
        self.assertIsNone(route("   ", self.config))


if __name__ == "__main__":
    unittest.main()
