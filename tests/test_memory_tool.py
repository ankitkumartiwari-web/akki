import tempfile
import unittest
from pathlib import Path

from akki.storage import Storage
from akki.tools.memory import remember_fact


class MemoryToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "memories.db")

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def test_remember_fact_persists(self) -> None:
        result = remember_fact("AKKI is local-first", storage=self.storage)
        self.assertTrue(result.ok)
        self.assertIn("AKKI is local-first", self.storage.memories()[0][1])

    def test_remember_fact_requires_storage(self) -> None:
        result = remember_fact("x", storage=None)
        self.assertFalse(result.ok)

    def test_remember_fact_rejects_empty(self) -> None:
        result = remember_fact("   ", storage=self.storage)
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
