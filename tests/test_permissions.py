import unittest

from akki.permissions import ask_confirmation


class AskConfirmationTests(unittest.TestCase):
    def test_returns_false_when_input_is_unavailable(self) -> None:
        def unavailable(_prompt: str) -> str:
            raise RuntimeError("input(): lost sys.stdin")

        self.assertFalse(ask_confirmation("Run tool?", input_fn=unavailable))

    def test_accepts_yes(self) -> None:
        self.assertTrue(ask_confirmation("Run tool?", input_fn=lambda _: " yes "))

    def test_rejects_no(self) -> None:
        self.assertFalse(ask_confirmation("Run tool?", input_fn=lambda _: "no"))
