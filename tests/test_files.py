import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akki.config import Config
from akki.tools.files import find_files, open_path, search_paths


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


if __name__ == "__main__":
    unittest.main()
