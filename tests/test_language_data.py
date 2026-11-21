import json
import unittest
from pathlib import Path

from akki import voice
from akki.language import is_latin_hindi


DATA_DIR = Path(__file__).resolve().parent / "data"


def load_jsonl(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class LanguageDataTests(unittest.TestCase):
    def test_names_and_loanwords_set_is_complete(self) -> None:
        items = load_jsonl("names_loanwords.jsonl")
        names = [item for item in items if item["category"] == "name"]
        loanwords = [item for item in items if item["category"] == "loanword"]
        self.assertEqual(len(names), 20)
        self.assertEqual(len(loanwords), 20)
        self.assertEqual(len(items), len({item["text"] for item in items}))
        for item in items:
            self.assertTrue(item["text"])
            self.assertEqual(item["expected"], item["text"])
            self.assertTrue(item["pronunciation_hint"])

    def test_english_voice_preserves_names_and_loanwords(self) -> None:
        for item in load_jsonl("names_loanwords.jsonl"):
            with self.subTest(text=item["text"]):
                self.assertEqual(
                    voice.normalize_name_pronunciation(
                        item["text"], "en-IN-PrabhatNeural"
                    ),
                    item["text"],
                )

    def test_hinglish_mixed_set_is_detected(self) -> None:
        items = load_jsonl("hinglish_mixed.jsonl")
        self.assertEqual(len(items), 10)
        for item in items:
            with self.subTest(text=item["text"]):
                self.assertEqual(item["category"], "mixed")
                self.assertTrue(is_latin_hindi(item["text"]))
                self.assertEqual(
                    voice.normalize_name_pronunciation(
                        item["text"], "en-IN-PrabhatNeural"
                    ),
                    item["text"],
                )


if __name__ == "__main__":
    unittest.main()
