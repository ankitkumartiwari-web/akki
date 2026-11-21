import unittest

from akki.config import Config
from akki import planner
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
        self.assertEqual(route("lock kar do", self.config).tool, "lock_screen")
        self.assertEqual(route("screen lock karo", self.config).tool, "lock_screen")
        self.assertEqual(route("mera screen lock kar do", self.config).tool, "lock_screen")
        self.assertEqual(route("स्क्रीन लॉक करो", self.config).tool, "lock_screen")
        self.assertIsNone(route("unlock screen", self.config))
        self.assertEqual(route("clipboard", self.config).tool, "clipboard_read")
        request = route("clipboard write hello world", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "clipboard_write")
        self.assertEqual(request.args["text"], "hello world")

    def test_file_details_requests(self) -> None:
        request = route("read file README.md", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "read_file")
        self.assertEqual(request.args["target"], "README.md")

        request = route("show details of my desktop", self.config)
        self.assertEqual(request.tool, "inspect_path")
        self.assertEqual(request.args["target"], "my desktop")

        request = route("list all files in my projects", self.config)
        self.assertEqual(request.tool, "list_folder")
        self.assertEqual(request.args["target"], "projects")
        self.assertTrue(request.args["recursive"])

        request = route("desktop ki files batao", self.config)
        self.assertEqual(request.tool, "list_folder")
        self.assertEqual(request.args["target"], "desktop")

        request = route("README.md file padho", self.config)
        self.assertEqual(request.tool, "read_file")

        request = route("fetch all the details from my files", self.config)
        self.assertEqual(request.tool, "inspect_path")
        self.assertEqual(request.args["target"], "my files")

    def test_extract_folder_info_request(self) -> None:
        request = route(r"extract info from folder C:\Users\ankit\Desktop", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "inspect_path")
        self.assertEqual(request.args["target"], r"C:\Users\ankit\Desktop")

    def test_compose_message_requests(self) -> None:
        request = route("compose message I will be late by ten minutes", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "compose_message")
        self.assertEqual(request.args["text"], "I will be late by ten minutes")

        request = route("message: kal meeting hai", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "compose_message")
        self.assertEqual(request.args["text"], "kal meeting hai")

        request = route("message kal meeting hai likho", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "compose_message")

    def test_remember_requests(self) -> None:
        request = route("remember that AKKI is local-first", self.config)
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "remember_fact")
        self.assertEqual(request.args["fact"], "AKKI is local-first")

        request = route(
            "store important info in memory for remainder: AKKI is local-first",
            self.config,
        )
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "remember_fact")
        self.assertEqual(request.args["fact"], "AKKI is local-first")

    def test_long_multi_step_request(self) -> None:
        text = (
            r"open folder C:\Users\ankit\Desktop then "
            r"extract info from folder C:\Users\ankit\Desktop then "
            "remember that AKKI is local-first"
        )
        requests = planner.plan_steps(text, self.config)
        self.assertEqual(
            [request.tool for request in requests],
            ["open_path", "inspect_path", "remember_fact"],
        )

    def test_unknown_request(self) -> None:
        self.assertIsNone(route("what is the weather tomorrow", self.config))

    def test_empty_request(self) -> None:
        self.assertIsNone(route("   ", self.config))


if __name__ == "__main__":
    unittest.main()
