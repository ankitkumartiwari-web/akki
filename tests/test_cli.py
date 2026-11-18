import contextlib
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import akki.cli as cli_module
from akki.cli import (
    build_registry,
    handle,
    is_latin_hindi,
    repl,
    speak_text,
)
from akki.config import Config
from akki.conversation import Conversation
from akki.llm import FallbackOutcome
from akki.models import ActionLevel, ActionRequest, ToolResult
from akki.registry import ToolRegistry
from akki.storage import Storage


class HandleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "akki.db")
        self.config = Config.default()
        self.config.llm.local_enabled = False
        self.registry = build_registry(self.config)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_cli_exposes_voice_capture_push(self) -> None:
        self.assertTrue(callable(cli_module.capture_push))

    def test_akki_change_toggles_nsfw_mode(self) -> None:
        with mock.patch("akki.cli.save_config"):
            first = handle(
                "akki change",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
            self.assertTrue(first.ok)
            self.assertEqual(self.config.profile, "nsfw")
            second = handle(
                "hey akki, change",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
            self.assertTrue(second.ok)
            self.assertEqual(self.config.profile, "sovereign")

    def test_akki_change_to_nsfw_sets_mode_explicitly(self) -> None:
        with mock.patch("akki.cli.save_config"):
            result = handle(
                "akki change to nsfw",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertTrue(result.ok)
        self.assertEqual(self.config.profile, "nsfw")
        self.assertIn("nsfw", result.message.lower())

    def test_akki_change_accepts_speech_to_text_mishearing(self) -> None:
        with mock.patch("akki.cli.save_config"):
            result = handle(
                "A key change.",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertTrue(result.ok)
        self.assertEqual(self.config.profile, "nsfw")

    def test_handle_executes_multi_step_plan(self) -> None:
        calls: list[tuple[str, str | None]] = []
        registry = ToolRegistry()
        registry.register(
            "launch_app",
            "launch",
            ActionLevel.REVERSIBLE,
            lambda alias: calls.append(("launch", alias))
            or ToolResult.success(f"opened {alias}"),
        )
        registry.register(
            "screenshot",
            "shot",
            ActionLevel.READ_ONLY,
            lambda: calls.append(("shot", None)) or ToolResult.success("captured"),
        )
        result = handle(
            "open notepad then take a screenshot",
            self.config,
            registry,
            Conversation(),
            self.storage,
        )
        self.assertTrue(result.ok)
        self.assertEqual(calls, [("launch", "notepad"), ("shot", None)])
        self.assertEqual(len(result.data["steps"]), 2)

    def test_cloud_reply_is_cached(self) -> None:
        with mock.patch(
            "akki.cli.ask_cloud", return_value=FallbackOutcome(text="something")
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
            "akki.cli.ask_cloud", return_value=FallbackOutcome(text="something")
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
            "akki.cli.ask_cloud", return_value=FallbackOutcome(text="ok")
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
            "akki.cli.ask_cloud", return_value=FallbackOutcome(text="fresh")
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
        self.config.voice.wake_enabled = False
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
                "akki.cli.ask_cloud",
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
        self.config.voice.wake_enabled = False
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

    def test_repl_voice_indian_persists(self) -> None:
        self.config.voice.wake_enabled = False
        config_file = Path(self.temp.name) / "config.json"
        with mock.patch(
            "builtins.input",
            side_effect=[":voice indian", ":quit"],
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                code = repl(
                    self.config, self.registry, self.storage, config_file
                )
        self.assertEqual(code, 0)
        self.assertEqual(self.config.voice.tts_engine, "edge")
        self.assertEqual(self.config.voice.edge_voice, "en-IN-PrabhatNeural")
        self.assertTrue(self.config.voice.auto_speak)
        self.assertTrue(config_file.exists())

    def test_speak_text_uses_nsfw_voice(self) -> None:
        self.config.profile = "nsfw"
        self.config.voice.tts_engine = "edge"
        self.config.voice.edge_voice = "en-IN-PrabhatNeural"
        self.config.voice.nsfw_edge_voice = "en-IN-NeerjaExpressiveNeural"
        with mock.patch("akki.cli.speak") as speak:
            speak_text("hello", self.config)
        self.assertEqual(
            speak.call_args.kwargs["edge_voice"],
            "en-IN-NeerjaExpressiveNeural",
        )

    def test_speak_text_uses_hindi_voice_for_devanagari(self) -> None:
        self.config.voice.tts_engine = "edge"
        self.config.voice.edge_voice = "en-IN-PrabhatNeural"
        self.config.voice.hindi_edge_voice = "hi-IN-MadhurNeural"
        with mock.patch("akki.cli.speak") as speak:
            speak_text("नमस्ते, मैं आपकी मदद कर सकता हूँ।", self.config)
        self.assertEqual(
            speak.call_args.kwargs["edge_voice"], "hi-IN-MadhurNeural"
        )

    def test_speak_text_uses_nsfw_hindi_voice_for_devanagari(self) -> None:
        self.config.profile = "nsfw"
        self.config.voice.tts_engine = "edge"
        self.config.voice.nsfw_edge_voice = "en-IN-NeerjaExpressiveNeural"
        self.config.voice.nsfw_hindi_edge_voice = "hi-IN-SwaraNeural"
        with mock.patch("akki.cli.speak") as speak:
            speak_text("नमस्ते", self.config)
        self.assertEqual(
            speak.call_args.kwargs["edge_voice"], "hi-IN-SwaraNeural"
        )

    def test_speak_text_uses_hindi_voice_for_latin_hinglish(self) -> None:
        self.config.profile = "nsfw"
        self.config.voice.tts_engine = "edge"
        self.config.voice.nsfw_edge_voice = "en-IN-NeerjaExpressiveNeural"
        self.config.voice.nsfw_hindi_edge_voice = "hi-IN-SwaraNeural"
        with mock.patch("akki.cli.speak") as speak:
            speak_text(
                "Mai tumhare saath baat karna chahti hoon, bahut maza aayega.",
                self.config,
            )
        self.assertEqual(
            speak.call_args.kwargs["edge_voice"], "hi-IN-SwaraNeural"
        )

    def test_latin_hindi_detection(self) -> None:
        self.assertTrue(is_latin_hindi("Main tumhare saath baat karna chahti hoon"))
        self.assertTrue(is_latin_hindi("kya hai yeh, mujhe batao"))
        self.assertFalse(is_latin_hindi("Hello there, how are you today?"))
        self.assertFalse(is_latin_hindi("Open the folder and find the file"))

    def test_repl_wake_on_starts_hotkey_capture_pipeline(self) -> None:
        self.config.voice.wake_enabled = True
        self.config.voice.hotkey_enabled = False

        class DummyWakeListener:
            def __init__(
                self, callback: object, *args: object, **kwargs: object
            ) -> None:
                self.callback = callback
                self.phrase = str(kwargs.get("phrase") or "")
                self.active = True

            def start(self) -> None:
                return None

            def stop(self) -> None:
                return None

        class DummyHotkeyListener:
            def __init__(
                self, callback: object, hotkey: str = "ctrl+space"
            ) -> None:
                self.callback = callback
                self.hotkey = hotkey
                self.active = False

            def start(self) -> None:
                return None

            def stop(self) -> None:
                return None

        with (
            mock.patch("akki.cli.WakeWordListener", DummyWakeListener),
            mock.patch("akki.cli.HotkeyListener", DummyHotkeyListener),
            mock.patch("akki.cli.hotkey_supported", return_value=True),
            mock.patch("akki.cli.wake_supported", return_value=True),
            mock.patch("builtins.input", side_effect=[":quit"]),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                code = repl(self.config, self.registry, self.storage, None)
        self.assertEqual(code, 0)

    def test_wake_keeps_listening_until_bye_akki(self) -> None:
        self.config.voice.wake_enabled = True
        self.config.voice.hotkey_enabled = True
        self.config.voice.auto_speak = False
        self.config.web.enabled = False
        self.config.desktop.tray_enabled = False
        self.config.desktop.widget_enabled = False
        self.config.desktop.bubble_enabled = False
        self.config.alerts.enabled = False
        self.config.llm.local_enabled = False

        calls: list[str] = []
        done = threading.Event()

        class FakeWake:
            fired = False

            def __init__(self, callback: object, *args: object, **kwargs: object) -> None:
                self.callback = callback
                self.phrase = str(kwargs.get("phrase") or "")
                self.active = False

            def start(self) -> None:
                self.active = True
                if not FakeWake.fired:
                    FakeWake.fired = True
                    threading.Thread(target=self._fire, daemon=True).start()

            def _fire(self) -> None:
                time.sleep(0.05)
                self.callback()  # type: ignore[operator]

            def stop(self) -> None:
                self.active = False

        class FakeHotkey:
            def __init__(self, callback: object, hotkey: str = "ctrl+space") -> None:
                self.callback = callback
                self.hotkey = hotkey
                self.active = False

            def start(self) -> None:
                self.active = True

            def stop(self) -> None:
                self.active = False

        transcripts = iter(["tell me a joke", "what is the time", "bye akki"])

        def fake_capture_push(*args: object, **kwargs: object) -> tuple[str, Path]:
            text = next(transcripts)
            if text == "bye akki":
                threading.Timer(0.2, done.set).start()
            return text, Path("fake.wav")

        def fake_respond(text: str, *args: object, **kwargs: object) -> ToolResult:
            calls.append(text)
            return ToolResult.success("ok")

        def fake_input(prompt: str = "") -> str:
            if not done.wait(5):
                raise AssertionError("conversation did not finish")
            raise EOFError

        with (
            mock.patch("akki.cli.WakeWordListener", FakeWake),
            mock.patch("akki.cli.HotkeyListener", FakeHotkey),
            mock.patch("akki.cli.hotkey_supported", return_value=True),
            mock.patch("akki.cli.wake_supported", return_value=True),
            mock.patch("akki.cli.capture_push", fake_capture_push),
            mock.patch("akki.cli.respond", fake_respond),
            mock.patch("builtins.input", fake_input),
            mock.patch("sys.stdin.isatty", return_value=False),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = repl(self.config, self.registry, self.storage, None)
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["tell me a joke", "what is the time"])
        self.assertTrue(done.is_set())

    def test_hotkey_keeps_listening_until_bye_akki(self) -> None:
        self.config.voice.wake_enabled = False
        self.config.voice.hotkey_enabled = True
        self.config.voice.auto_speak = False
        self.config.web.enabled = False
        self.config.desktop.tray_enabled = False
        self.config.desktop.widget_enabled = False
        self.config.desktop.bubble_enabled = False
        self.config.alerts.enabled = False
        self.config.llm.local_enabled = False

        calls: list[str] = []
        done = threading.Event()

        class FakeHotkey:
            def __init__(self, callback: object, hotkey: str = "ctrl+space") -> None:
                self.callback = callback
                self.hotkey = hotkey
                self.active = False

            def start(self) -> None:
                self.active = True
                threading.Thread(target=self._fire, daemon=True).start()

            def _fire(self) -> None:
                time.sleep(0.05)
                self.callback()  # type: ignore[operator]

            def stop(self) -> None:
                self.active = False

        transcripts = iter(["tell me a joke", "what is the time", "bye akki"])

        def fake_capture_push(*args: object, **kwargs: object) -> tuple[str, Path]:
            text = next(transcripts)
            if text == "bye akki":
                threading.Timer(0.2, done.set).start()
            return text, Path("fake.wav")

        def fake_respond(text: str, *args: object, **kwargs: object) -> ToolResult:
            calls.append(text)
            return ToolResult.success("ok")

        def fake_kbhit() -> bool:
            return done.is_set()

        def fake_getwch() -> str:
            return "\x03"

        with (
            mock.patch("akki.cli.HotkeyListener", FakeHotkey),
            mock.patch("akki.cli.hotkey_supported", return_value=True),
            mock.patch("akki.cli.wake_supported", return_value=True),
            mock.patch("akki.cli.capture_push", fake_capture_push),
            mock.patch("akki.cli.respond", fake_respond),
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("msvcrt.kbhit", fake_kbhit),
            mock.patch("msvcrt.getwch", fake_getwch),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = repl(self.config, self.registry, None, None)
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["tell me a joke", "what is the time"])
        self.assertTrue(done.is_set())

    def test_local_tier_runs_first(self) -> None:
        self.config.llm.local_enabled = True
        self.config.llm.local_first = True
        with mock.patch(
            "akki.cli.ask_local", return_value=FallbackOutcome(text="local answer")
        ) as local:
            with mock.patch("akki.cli.ask_cloud") as cloud:
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

    def test_nsfw_profile_runs_local_tier_first(self) -> None:
        self.config.profile = "nsfw"
        self.config.llm.local_enabled = True
        self.config.llm.local_first = False
        with mock.patch(
            "akki.cli.ask_local", return_value=FallbackOutcome(text="local answer")
        ) as local:
            with mock.patch("akki.cli.ask_cloud") as cloud:
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

    def test_nsfw_cloud_model_takes_priority(self) -> None:
        self.config.profile = "nsfw"
        self.config.llm.local_enabled = True
        self.config.llm.nsfw_model = "vendor/nsfw-model"
        with mock.patch("akki.cli.ask_local") as local:
            with mock.patch(
                "akki.cli.ask_cloud",
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
        local.assert_not_called()

    def test_unsupported_script_reply_is_retried_on_next_tier(self) -> None:
        self.config.llm.local_enabled = True
        self.config.llm.local_first = True
        hebrew = "שלום, מה שלומך היום"
        with mock.patch(
            "akki.cli.ask_local", return_value=FallbackOutcome(text=hebrew)
        ):
            with mock.patch(
                "akki.cli.ask_cloud",
                return_value=FallbackOutcome(text="Hello, how are you?"),
            ):
                result = handle(
                    "hi there, unsupported script probe",
                    self.config,
                    self.registry,
                    Conversation(),
                    self.storage,
                )
        self.assertEqual(result.message, "Hello, how are you?")
        self.assertNotIn("ש", result.message)

    def test_unsupported_script_only_gives_friendly_fallback(self) -> None:
        self.config.llm.local_enabled = True
        self.config.llm.enabled = False
        with mock.patch(
            "akki.cli.ask_local",
            return_value=FallbackOutcome(text="שלום חבר"),
        ):
            result = handle(
                "hi again, unsupported script probe two",
                self.config,
                self.registry,
                Conversation(),
                self.storage,
            )
        self.assertTrue(result.ok)
        self.assertEqual(
            result.message, "Sorry, I didn't catch that. Please say it again."
        )

    def test_local_failure_falls_back_to_cloud(self) -> None:
        self.config.llm.local_enabled = True
        self.config.llm.local_first = True
        with mock.patch(
            "akki.cli.ask_local",
            return_value=FallbackOutcome(error="connection refused"),
        ):
            with mock.patch(
                "akki.cli.ask_cloud",
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
        self.config.llm.local_first = True
        with mock.patch(
            "akki.cli.ask_local", return_value=FallbackOutcome(text="local answer")
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
