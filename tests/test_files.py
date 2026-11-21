import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akki.config import Config
from akki.tools.files import (
    find_files,
    inspect_path,
    list_folder,
    open_path,
    read_file,
    search_paths,
)


class FileSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Alpha" / "FinoraProject").mkdir(parents=True)
        (self.root / "Alpha" / "FinoraProject" / "main.py").write_text("print('hi')")
        (self.root / "Beta").mkdir()
        (self.root / "Beta" / "readme.md").write_text("notes")
        self.config = Config(
            search_roots=[self.root],
            max_depth=5,
            max_results=10,
            timeout_seconds=2.0,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_search_is_case_insensitive(self) -> None:
        matches = search_paths("finora", self.config)
        self.assertTrue(any(p.name == "FinoraProject" for p in matches))

    def test_find_files_returns_matches(self) -> None:
        result = find_files("readme", config=self.config)
        self.assertTrue(result.ok)
        self.assertTrue(any("readme.md" in m for m in result.data["matches"]))

    def test_find_files_missing(self) -> None:
        result = find_files("does-not-exist", config=self.config)
        self.assertFalse(result.ok)
        self.assertIn("no matches", result.message)

    def test_depth_limit(self) -> None:
        shallow = Config(search_roots=[self.root], max_depth=0, timeout_seconds=2.0)
        matches = search_paths("main.py", shallow)
        self.assertEqual(matches, [])

    def test_open_missing_path(self) -> None:
        result = open_path(str(self.root / "nope.txt"), config=self.config)
        self.assertFalse(result.ok)

    def test_open_path_uses_startfile(self) -> None:
        target = self.root / "Beta" / "readme.md"
        with mock.patch("os.startfile", create=True) as startfile:
            result = open_path(str(target), config=self.config)
        self.assertTrue(result.ok)
        startfile.assert_called_once_with(str(target))
        self.assertFalse(result.verified)

    def test_list_folder_includes_details(self) -> None:
        result = list_folder("Beta", config=self.config)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["entries"][0]["name"], "readme.md")
        self.assertEqual(result.data["entries"][0]["type"], "file")
        self.assertIn("readme.md", result.message)
        self.assertIn("B", result.message)

    def test_read_file_returns_text_and_metadata(self) -> None:
        result = read_file("readme", config=self.config)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["text"], "notes")
        self.assertEqual(result.data["lines"], 1)
        self.assertEqual(result.data["name"], "readme.md")
        self.assertIn("notes", result.message)

    def test_inspect_path_reads_file_and_lists_folder(self) -> None:
        file_result = inspect_path("main.py", config=self.config)
        self.assertTrue(file_result.ok)
        self.assertEqual(file_result.data["text"], "print('hi')")
        folder_result = inspect_path("Alpha", config=self.config)
        self.assertTrue(folder_result.ok)
        self.assertTrue(folder_result.data["entries"])

    def test_list_all_configured_roots(self) -> None:
        result = list_folder("my files", config=self.config)
        self.assertTrue(result.ok)
        names = {entry["name"] for entry in result.data["entries"]}
        self.assertIn("Alpha", names)
        self.assertIn("Beta", names)

    def test_recursive_listing_respects_limit(self) -> None:
        result = list_folder("Alpha", config=self.config, recursive=True, limit=1)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data["entries"]), 1)
        self.assertTrue(result.data["truncated"])

    def test_desktop_alias_merges_local_and_onedrive_roots(self) -> None:
        local = self.root / "local" / "Desktop"
        cloud = self.root / "cloud" / "Desktop"
        local.mkdir(parents=True)
        cloud.mkdir(parents=True)
        (local / "local.txt").write_text("local", encoding="utf-8")
        (cloud / "cloud.txt").write_text("cloud", encoding="utf-8")
        config = Config(
            search_roots=[local, cloud], max_depth=2, timeout_seconds=2.0
        )
        result = list_folder("desktop", config=config)
        self.assertTrue(result.ok)
        names = {entry["name"] for entry in result.data["entries"]}
        self.assertEqual(names, {"local.txt", "cloud.txt"})


if __name__ == "__main__":
    unittest.main()
