import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akki.models import ToolResult
from akki.tools.messages import compose_message


class ComposeMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_compose_copies_and_saves_draft(self) -> None:
        with mock.patch("akki.tools.messages.database_path", return_value=self.root / "akki.db"):
            with mock.patch(
                "akki.tools.messages.clipboard_write",
                return_value=ToolResult.success("copied"),
            ):
                result = compose_message("  Hello from AKKI  ")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["text"], "Hello from AKKI")
        draft = Path(result.data["draft"])
        self.assertTrue(draft.exists())
        self.assertEqual(draft.read_text(encoding="utf-8").strip(), "Hello from AKKI")

    def test_clipboard_failure_keeps_draft(self) -> None:
        with mock.patch("akki.tools.messages.database_path", return_value=self.root / "akki.db"):
            with mock.patch(
                "akki.tools.messages.clipboard_write",
                return_value=ToolResult.failure("clipboard busy"),
            ):
                result = compose_message("hello")
        self.assertFalse(result.ok)
        self.assertTrue(Path(result.data["draft"]).exists())
        self.assertIn("clipboard", result.message)

    def test_empty_message_fails(self) -> None:
        self.assertFalse(compose_message("  ").ok)


if __name__ == "__main__":
    unittest.main()
