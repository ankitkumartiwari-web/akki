import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from odin.cli import build_registry, handle, repl
from odin.config import Config
from odin.conversation import Conversation
from odin.llm import FallbackOutcome
from odin.storage import Storage


class HandleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "odin.db")
        self.config = Config.default()
        self.config.llm.local_enabled = False
        self.registry = build_registry(self.config)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_cloud_reply_is_cached(self) -> None:
        with mock.patch(
            "odin.cli.ask_cloud", return_value=FallbackOutcome(text="something")
        ) as ask:
            first = handle(
                "tell me something interesting",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
            second = handle(
                "tell me something interesting",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(first.message, "something")
        self.assertTrue(second.data.get("cached"))

    def test_cache_can_be_disabled(self) -> None:
        self.config.llm.cache_ttl_seconds = 0
        with mock.patch(
            "odin.cli.ask_cloud", return_value=FallbackOutcome(text="something")
        ) as ask:
            for _ in range(2):
                handle(
                    "tell me something interesting",
                    self.config,
                    self.registry,
                    Conversation(),
                    self.storage,
                )
        self.assertEqual(ask.call_count, 2)

    def test_memories_are_passed_to_cloud(self) -> None:
        self.storage.remember("prefers dark mode")
        with mock.patch(
            "odin.cli.ask_cloud", return_value=FallbackOutcome(text="ok")
        ) as ask:
            handle(
                "what do you know about me",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertEqual(ask.call_args.kwargs["memory"], ["prefers dark mode"])

    def test_feedback_is_passed_to_model(self) -> None:
        self.storage.add_feedback(
            1, note="keep it short", prompt="hi", response="Short answer."
        )
        with mock.patch(
            "odin.cli.ask_cloud", return_value=FallbackOutcome(text="fresh")
        ) as ask:
            handle(
                "tell me something interesting",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        feedback = ask.call_args.kwargs["feedback"]
        self.assertEqual(feedback[0]["note"], "keep it short")

    def test_repl_records_reward_and_punishment(self) -> None:
        with mock.patch(
            "builtins.input",
            side_effect=[
                "tell me something interesting",
                ":good short and clear",
                ":bad too vague",
                ":quit",
            ],
        ):
            with mock.patch(
                "odin.cli.ask_cloud",
                return_value=FallbackOutcome(text="something useful"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = repl(self.config, self.registry, self.storage, None)
        self.assertEqual(code, 0)
        stats = self.storage.feedback_stats()
        self.assertEqual(stats["positive"], 1)
        self.assertEqual(stats["negative"], 1)
        self.assertEqual(stats["score"], 0)
        notes = {item["note"] for item in self.storage.recent_feedback(5)}
        self.assertEqual(notes, {"short and clear", "too vague"})

    def test_repl_stt_settings_persist(self) -> None:
        config_file = Path(self.temp.name) / "config.json"
        with mock.patch(
            "builtins.input",
            side_effect=[
                ":stt model base.en",
                ":stt language hi",
                ":stt",
                ":quit",
            ],
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                code = repl(
                    self.config, self.registry, self.storage, config_file
                )
        self.assertEqual(code, 0)
        self.assertEqual(self.config.voice.stt_model, "base.en")
        self.assertEqual(self.config.voice.stt_language, "hi")
        self.assertTrue(config_file.exists())

    def test_local_tier_runs_first(self) -> None:
        self.config.llm.local_enabled = True
        with mock.patch(
            "odin.cli.ask_local", return_value=FallbackOutcome(text="local answer")
        ) as local:
            with mock.patch("odin.cli.ask_cloud") as cloud:
                result = handle(
                    "tell me something interesting",
                    self.config,
                    self.registry,
                    Conversation(),
                    self.storage,
                )
        self.assertEqual(result.message, "local answer")
        local.assert_called_once()
        cloud.assert_not_called()

    def test_local_failure_falls_back_to_cloud(self) -> None:
        self.config.llm.local_enabled = True
        with mock.patch(
            "odin.cli.ask_local",
            return_value=FallbackOutcome(error="connection refused"),
        ):
            with mock.patch(
                "odin.cli.ask_cloud",
                return_value=FallbackOutcome(text="cloud answer"),
            ) as cloud:
                result = handle(
                    "tell me something interesting",
                    self.config,
                    self.registry,
                    Conversation(),
                    self.storage,
                )
        self.assertEqual(result.message, "cloud answer")
        cloud.assert_called_once()

    def test_local_reply_is_cached(self) -> None:
        self.config.llm.local_enabled = True
        with mock.patch(
            "odin.cli.ask_local", return_value=FallbackOutcome(text="local answer")
        ) as local:
            handle(
                "tell me something interesting",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
            second = handle(
                "tell me something interesting",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertEqual(local.call_count, 1)
        self.assertTrue(second.data.get("cached"))
