import tempfile
import unittest
from pathlib import Path

from odin.storage import Storage, make_cache_key


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "odin.db"
        self.storage = Storage(self.db)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_memories_roundtrip(self) -> None:
        memory_id = self.storage.remember("prefers dark mode")
        self.assertEqual(self.storage.memories(), [(memory_id, "prefers dark mode")])
        self.assertTrue(self.storage.forget(memory_id))
        self.assertEqual(self.storage.memories(), [])
        self.assertFalse(self.storage.forget(memory_id))

    def test_remember_is_idempotent(self) -> None:
        first = self.storage.remember("likes tea")
        second = self.storage.remember("  likes   tea  ")
        self.assertEqual(first, second)

    def test_turns_persist_per_session(self) -> None:
        first = self.storage.start_session()
        second = self.storage.start_session()
        self.storage.add_turn(first, "user", "hello")
        self.storage.add_turn(first, "assistant", "hi")
        self.storage.add_turn(second, "user", "later")
        self.assertEqual(
            self.storage.recent_turns(session_id=first),
            [("user", "hello"), ("assistant", "hi")],
        )
        self.assertEqual(
            self.storage.recent_turns(), [("user", "hello"), ("assistant", "hi"), ("user", "later")]
        )

    def test_cache_roundtrip_and_expiry(self) -> None:
        self.storage.cache_put("k", "value", 3600)
        self.assertEqual(self.storage.cache_get("k"), "value")
        self.storage.cache_put("short", "gone", -1)
        self.assertIsNone(self.storage.cache_get("short"))

    def test_cache_purge(self) -> None:
        self.storage.cache_put("k", "value", 3600)
        self.assertEqual(self.storage.purge_cache(expired_only=False), 1)
        self.assertIsNone(self.storage.cache_get("k"))

    def test_cache_key_depends_on_history(self) -> None:
        base = make_cache_key("openrouter", "free", "system", [], "hi")
        with_history = make_cache_key(
            "openrouter", "free", "system", [{"role": "user", "content": "x"}], "hi"
        )
        self.assertNotEqual(base, with_history)

    def test_feedback_roundtrip_and_stats(self) -> None:
        session = self.storage.start_session()
        reward = self.storage.add_feedback(
            1,
            note="  short and useful ",
            prompt="what time is it",
            response="It is noon.",
            session_id=session,
        )
        self.storage.add_feedback(
            -1, note="too long", prompt="hello", response="A very long reply."
        )
        self.assertEqual(
            self.storage.feedback_stats(),
            {"positive": 1, "negative": 1, "total": 2, "score": 0},
        )
        recent = self.storage.recent_feedback(2)
        self.assertEqual(recent[0]["note"], "too long")
        self.assertEqual(recent[1]["id"], reward)
        self.assertEqual(recent[1]["session_id"], session)
        self.assertEqual(recent[1]["note"], "short and useful")
        self.assertEqual(len(self.storage.recent_feedback(1, rating=1)), 1)
        self.assertEqual(self.storage.clear_feedback(), 2)
        self.assertEqual(self.storage.feedback_stats()["total"], 0)

    def test_feedback_rejects_invalid_rating(self) -> None:
        with self.assertRaises(ValueError):
            self.storage.add_feedback(0)
