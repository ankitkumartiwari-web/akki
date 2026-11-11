import base64
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from odin import voice


class VoiceTests(unittest.TestCase):
    def test_clean_for_speech_removes_markdown_and_emoji(self) -> None:
        self.assertEqual(
            voice.clean_for_speech('**Hi** there 😊'), "Hi there"
        )
        self.assertEqual(
            voice.clean_for_speech("`code` [link](http://x) :smile:"), "code link"
        )
        self.assertEqual(
            voice.clean_for_speech("## Title\n- item one\n- item two"),
            "Title item one item two",
        )
        self.assertEqual(voice.clean_for_speech("** ** 😊"), "")

    def test_speak_sanitizes_before_synthesis(self) -> None:
        with mock.patch("odin.voice._speak_sapi") as sapi:
            voice.speak('**Hello** 😊')
        sapi.assert_called_once()
        self.assertEqual(sapi.call_args.args[0], "Hello")

    def test_catalog_contains_default_voice(self) -> None:
        voices = dict(voice.piper_catalog())
        self.assertIn(voice.DEFAULT_PIPER_VOICE, voices)
        self.assertIn("en_GB-alba-medium", voices)
        self.assertIn("hi_IN-pratham-medium", voices)
        self.assertIn("mr_IN-google-medium", voices)

    def test_aliases_resolve_to_indian_voices(self) -> None:
        self.assertEqual(
            voice.resolve_voice_id("bhojpuri"), "hi_IN-pratham-medium"
        )
        self.assertEqual(
            voice.resolve_voice_id("Hindi-Female"), "hi_IN-priyamvada-medium"
        )
        self.assertEqual(
            voice.resolve_voice_id("marathi"), "mr_IN-google-medium"
        )
        self.assertEqual(
            voice.resolve_voice_id("en_US-amy-medium"), "en_US-amy-medium"
        )

    def test_piper_command_adds_speaker_only_when_set(self) -> None:
        args = (Path("piper"), Path("m"), Path("c"), Path("o"), 1.0)
        self.assertNotIn("--speaker", voice.piper_command(*args))
        command = voice.piper_command(*args, speaker=3)
        self.assertEqual(command[-2:], ["--speaker", "3"])

    def test_piper_python_command_uses_file_input(self) -> None:
        command = voice.piper_python_command(
            Path("m.onnx"), Path("m.json"), Path("t.txt"), Path("o.wav"), 1.0, 2
        )
        self.assertEqual(command[1:3], ["-m", "piper"])
        self.assertIn("-i", command)
        self.assertEqual(command[-2:], ["-s", "2"])

    def test_speech_script_embeds_text(self) -> None:
        script = voice.speech_script("Hello there", rate=2, volume=50)
        encoded = base64.b64encode("Hello there".encode("utf-8")).decode("ascii")
        self.assertIn(encoded, script)
        self.assertIn("$s.Rate = 2", script)
        self.assertIn("$s.Volume = 50", script)

    def test_speech_script_clamps_ranges(self) -> None:
        script = voice.speech_script("x", rate=99, volume=-5)
        self.assertIn("$s.Rate = 10", script)
        self.assertIn("$s.Volume = 0", script)

    def test_voice_name_quotes_are_escaped(self) -> None:
        script = voice.speech_script("x", voice_name="Bob's Voice")
        self.assertIn("Bob''s Voice", script)

    def test_speak_ignores_empty_text(self) -> None:
        with mock.patch("odin.voice._powershell") as shell:
            voice.speak("   ")
        shell.assert_not_called()

    def test_speak_raises_on_failure(self) -> None:
        with mock.patch("odin.voice.os.name", "nt"):
            with mock.patch("odin.voice._powershell") as shell:
                shell.return_value = subprocess.CompletedProcess([], 1, "", "boom")
                with self.assertRaises(voice.VoiceError):
                    voice.speak("hi")

    def test_list_voices_parses_output(self) -> None:
        with mock.patch("odin.voice.os.name", "nt"):
            with mock.patch("odin.voice._powershell") as shell:
                shell.return_value = subprocess.CompletedProcess(
                    [], 0, "Zira\nDavid\n", ""
                )
                self.assertEqual(voice.list_voices(), ["Zira", "David"])

    def test_transcribe_without_faster_whisper(self) -> None:
        voice._models.clear()
        with mock.patch.dict("sys.modules", {"faster_whisper": None}):
            with self.assertRaises(voice.VoiceError):
                voice.transcribe("missing.wav")
        voice._models.clear()

    def test_transcribe_auto_detects_language(self) -> None:
        class FakeModel:
            def __init__(self) -> None:
                self.calls = []

            def transcribe(self, path, **kwargs):
                self.calls.append(kwargs)
                return [SimpleNamespace(text=" namaste ")], None

        fake = FakeModel()
        with mock.patch("odin.voice._whisper_model", return_value=fake):
            text = voice.transcribe("x.wav", "small", "auto")
        self.assertEqual(text, "namaste")
        self.assertIsNone(fake.calls[0]["language"])

    def test_transcribe_forces_language_and_english_model(self) -> None:
        class FakeModel:
            def __init__(self) -> None:
                self.calls = []

            def transcribe(self, path, **kwargs):
                self.calls.append(kwargs)
                return [SimpleNamespace(text=" ok ")], None

        fake = FakeModel()
        with mock.patch("odin.voice._whisper_model", return_value=fake):
            voice.transcribe("x.wav", "small", "mr")
            voice.transcribe("x.wav", "base.en", "auto")
        self.assertEqual(fake.calls[0]["language"], "mr")
        self.assertEqual(fake.calls[1]["language"], "en")

    def test_record_without_sounddevice(self) -> None:
        with mock.patch.dict("sys.modules", {"sounddevice": None}):
            with self.assertRaises(voice.VoiceError):
                voice.record_to_wav(Path("missing.wav"))

    def test_push_record_without_sounddevice(self) -> None:
        with mock.patch.dict("sys.modules", {"sounddevice": None}):
            with self.assertRaises(voice.VoiceError):
                voice.record_until_silence(Path("missing.wav"))

    def test_piper_voice_urls(self) -> None:
        model, config = voice.piper_voice_urls("en_US-lessac-medium")
        self.assertTrue(
            model.endswith("en/en_US/lessac/medium/en_US-lessac-medium.onnx")
        )
        self.assertTrue(config.endswith("en_US-lessac-medium.onnx.json"))
        with self.assertRaises(voice.VoiceError):
            voice.piper_voice_urls("bad")

    def test_speak_dispatches_to_piper(self) -> None:
        with mock.patch("odin.voice.speak_piper") as piper:
            voice.speak("hello", engine="piper", piper_voice="en_US-lessac-medium")
        piper.assert_called_once()

    def test_speak_piper_requires_install(self) -> None:
        with mock.patch("odin.voice.os.name", "nt"):
            with mock.patch("odin.voice.piper_exe", return_value=None):
                with mock.patch(
                    "odin.voice.piper_python_available", return_value=False
                ):
                    with self.assertRaises(voice.VoiceError):
                        voice.speak_piper("hello")

    def test_unknown_engine_raises(self) -> None:
        with self.assertRaises(voice.VoiceError):
            voice.speak("hello", engine="bogus")
