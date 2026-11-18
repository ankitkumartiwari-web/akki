import tempfile
import unittest
from pathlib import Path

from akki import knowledge
from akki.storage import Storage


class KnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / "akki.db")

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_chunk_text_overlaps_and_keeps_content(self) -> None:
        text = "First sentence. " * 200
        chunks = knowledge.chunk_text(text, size=200, overlap=40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 220 for chunk in chunks))
        self.assertIn("First sentence", chunks[0])

    def test_index_search_and_remove(self) -> None:
        doc = self.root / "notes.md"
        doc.write_text(
            "The launch code for the Finora project is aurora.",
            encoding="utf-8",
        )
        indexed, skipped = knowledge.index_path(self.storage, doc)
        self.assertEqual((indexed, skipped), (1, 0))
        hits = knowledge.search(self.storage, "Finora launch")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["path"], str(doc.resolve()))
        context = knowledge.document_context(self.storage, "aurora")
        self.assertIn("aurora", context)
        self.assertEqual(knowledge.remove_document(self.storage, "1"), 1)
        self.assertEqual(knowledge.search(self.storage, "Finora"), [])

    def test_index_skips_unchanged_and_bad_paths(self) -> None:
        doc = self.root / "a.txt"
        doc.write_text("alpha beta", encoding="utf-8")
        knowledge.index_path(self.storage, doc)
        self.assertEqual(knowledge.index_path(self.storage, doc), (0, 1))
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.index_path(self.storage, self.root / "missing")
        self.assertEqual(knowledge.clear_documents(self.storage), 1)
        self.assertEqual(knowledge.list_documents(self.storage), [])

    def test_html_is_stripped(self) -> None:
        doc = self.root / "page.html"
        doc.write_text(
            "<html><style>x</style><body><h1>Title</h1><p>Hello world</p></body></html>",
            encoding="utf-8",
        )
        knowledge.index_path(self.storage, doc)
        hits = knowledge.search(self.storage, "Hello")
        self.assertTrue(hits)
        self.assertNotIn("style", str(hits[0]["text"]))
        self.assertIn("Title", str(hits[0]["text"]))


if __name__ == "__main__":
    unittest.main()
