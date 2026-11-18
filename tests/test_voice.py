import base64
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from akki import voice
from akki.wake import WakeWordListener, normalize_wake_word


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

    def test_clean_for_speech_removes_dot_runs(self) -> None:
        cleaned = voice.clean_for_speech("One... two… three • item")
        self.assertNotIn("...", cleaned)
        self.assertNotIn("…", cleaned)
        self.assertNotIn("•", cleaned)
        self.assertIn("One", cleaned)

    def test_speak_sanitizes_before_synthesis(self) -> None:
        with mock.patch("akki.voice._speak_sapi") as sapi:
            voice.speak('**Hello** 😊')
        sapi.assert_called_once()
        self.assertEqual(sapi.call_args.args[0], "Hello")

    def test_hindi_voice_normalizes_name_pronunciation(self) -> None:
        self.assertEqual(
            voice.normalize_name_pronunciation(
                "मैं आक्की हूँ", "hi-IN-MadhurNeural"
            ),
            "मैं अक्की हूँ",
        )
        self.assertEqual(
            voice.normalize_name_pronunciation("I am AKKI", "hi-IN-SwaraNeural"),
            "I am अक्की",
        )

    def test_english_voice_keeps_name_in_latin(self) -> None:
        self.assertEqual(
            voice.normalize_name_pronunciation(
                "I am आक्की", "en-IN-PrabhatNeural"
            ),
            "I am Akki",
        )
        self.assertEqual(
            voice.normalize_name_pronunciation(
                "I am Akki", "en-IN-PrabhatNeural"
            ),
            "I am Akki",
        )

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

    def test_speech_script_supports_pitch(self) -> None:
        script = voice.speech_script("Hello there", pitch=-25)
        self.assertIn("SpeakSsml", script)
        self.assertIn("pitch='-25%'", script)

    def test_piper_pitch_shift_lowers_and_slows_audio(self) -> None:
        import tempfile
        import wave

        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tone.wav"
            samples = (np.zeros(2000, dtype=np.int16) + 1000).tobytes()
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(22050)
                handle.writeframes(samples)
            voice._apply_piper_pitch(path, -20)
            with wave.open(str(path), "rb") as handle:
                self.assertEqual(handle.getframerate(), 22050)
                self.assertGreater(handle.getnframes(), 2000)

    def test_speech_script_clamps_ranges(self) -> None:
        script = voice.speech_script("x", rate=99, volume=-5)
        self.assertIn("$s.Rate = 10", script)
        self.assertIn("$s.Volume = 0", script)

    def test_voice_name_quotes_are_escaped(self) -> None:
        script = voice.speech_script("x", voice_name="Bob's Voice")
        self.assertIn("Bob''s Voice", script)

    def test_speak_ignores_empty_text(self) -> None:
        with mock.patch("akki.voice._powershell") as shell:
            voice.speak("   ")
        shell.assert_not_called()

    def test_speak_raises_on_failure(self) -> None:
        with mock.patch("akki.voice.os.name", "nt"):
            with mock.patch("akki.voice._powershell") as shell:
                shell.return_value = subprocess.CompletedProcess([], 1, "", "boom")
                with self.assertRaises(voice.VoiceError):
                    voice.speak("hi")

    def test_list_voices_parses_output(self) -> None:
        with mock.patch("akki.voice.os.name", "nt"):
            with mock.patch("akki.voice._powershell") as shell:
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
        with mock.patch("akki.voice._whisper_model", return_value=fake):
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
        with mock.patch("akki.voice._whisper_model", return_value=fake):
            voice.transcribe("x.wav", "small", "mr")
            voice.transcribe("x.wav", "base.en", "auto")
        self.assertEqual(fake.calls[0]["language"], "mr")
        self.assertEqual(fake.calls[1]["language"], "en")

    def test_transcribe_prefers_fast_english_model(self) -> None:
        class FakeModel:
            def transcribe(self, path, **kwargs):
                return [SimpleNamespace(text=" ok ")], None

        sizes = []

        def fake_model(size):
            sizes.append(size)
            return FakeModel()

        with mock.patch("akki.voice._whisper_model", side_effect=fake_model):
            voice.transcribe("x.wav", "small", "en")
            voice.transcribe("x.wav", "small", "mr")
            voice.transcribe("x.wav", "small", "auto")
        self.assertEqual(sizes, ["small.en", "small", "small"])

    def test_transcribe_rejects_whisper_hallucinations(self) -> None:
        class FakeModel:
            def transcribe(self, path, **kwargs):
                return [
                    SimpleNamespace(text=" The content of this video is very good.")
                ], None

        with mock.patch("akki.voice._whisper_model", return_value=FakeModel()):
            with self.assertRaises(voice.VoiceError):
                voice.transcribe("x.wav", "small", "en")

    def test_stt_prompt_biases_short_greetings(self) -> None:
        self.assertIn("Hey Akki", voice.STT_INITIAL_PROMPT)
        self.assertIn("hi", voice.STT_INITIAL_PROMPT)

    def test_record_without_sounddevice(self) -> None:
        with mock.patch.dict("sys.modules", {"sounddevice": None}):
            with self.assertRaises(voice.VoiceError):
                voice.record_to_wav(Path("missing.wav"))

    def test_push_record_without_sounddevice(self) -> None:
        with mock.patch.dict("sys.modules", {"sounddevice": None}):
            with self.assertRaises(voice.VoiceError):
                voice.record_until_silence(Path("missing.wav"))

    def test_wake_word_accepts_close_transcriptions(self) -> None:
        self.assertTrue(normalize_wake_word("Hey Akki, open notepad", "hey akki"))
        self.assertTrue(normalize_wake_word("akky", "hey akki"))
        self.assertTrue(normalize_wake_word("Akki", "hey akki"))
        self.assertTrue(normalize_wake_word("akki", "hey akki"))
        self.assertFalse(normalize_wake_word("hey there", "hey akki"))

    def test_wake_listener_keeps_running_after_empty_transcript(self) -> None:
        detected: list[bool] = []
        listener = WakeWordListener(lambda: detected.append(True))
        with (
            mock.patch(
                "akki.wake.voice.record_until_silence",
                return_value=(Path("x.wav"), True),
            ),
            mock.patch(
                "akki.wake.voice.transcribe",
                side_effect=[
                    voice.VoiceError("could not transcribe any speech"),
                    "hey akki",
                ],
            ),
        ):
            listener._run()
        self.assertEqual(detected, [True])

    def test_piper_voice_urls(self) -> None:
        model, config = voice.piper_voice_urls("en_US-lessac-medium")
        self.assertTrue(
            model.endswith("en/en_US/lessac/medium/en_US-lessac-medium.onnx")
        )
        self.assertTrue(config.endswith("en_US-lessac-medium.onnx.json"))
        with self.assertRaises(voice.VoiceError):
            voice.piper_voice_urls("bad")

    def test_speak_dispatches_to_piper(self) -> None:
        with mock.patch("akki.voice.speak_piper") as piper:
            voice.speak("hello", engine="piper", piper_voice="en_US-lessac-medium")
        piper.assert_called_once()

    def test_speak_dispatches_to_edge(self) -> None:
        with mock.patch("akki.voice.speak_edge") as edge:
            voice.speak(
                "hello",
                engine="edge",
                edge_voice="en-IN-PrabhatNeural",
            )
        edge.assert_called_once()

    def test_speak_edge_falls_back_to_piper(self) -> None:
        with mock.patch(
            "akki.voice.speak_edge",
            side_effect=voice.VoiceError("offline"),
        ):
            with mock.patch("akki.voice.speak_piper") as piper:
                voice.speak("hello", engine="edge")
        piper.assert_called_once()

    def test_speak_edge_playback_error_does_not_replay_via_piper(self) -> None:
        with mock.patch(
            "akki.voice.speak_edge",
            side_effect=voice.VoicePlaybackError("playback"),
        ):
            with mock.patch("akki.voice.speak_piper") as piper:
                with self.assertRaises(voice.VoicePlaybackError):
                    voice.speak("hello", engine="edge")
        piper.assert_not_called()

    def test_speak_piper_requires_install(self) -> None:
        with mock.patch("akki.voice.os.name", "nt"):
            with mock.patch("akki.voice.piper_exe", return_value=None):
                with mock.patch(
                    "akki.voice.piper_python_available", return_value=False
                ):
                    with self.assertRaises(voice.VoiceError):
                        voice.speak_piper("hello")

    def test_speech_chunks_split_sentences_and_long_text(self) -> None:
        self.assertEqual(
            voice._speech_chunks("One. Two! Three?"),
            ["One.", "Two!", "Three?"],
        )
        long_text = "word " * 40
        chunks = voice._speech_chunks(long_text, max_chars=40)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 40 for chunk in chunks))
        self.assertEqual(" ".join(chunks), long_text.strip())

    def test_speak_piper_prefers_cached_python_backend(self) -> None:
        with mock.patch("akki.voice.os.name", "nt"):
            with mock.patch("akki.voice.piper_python_available", return_value=True):
                with mock.patch(
                    "akki.voice.piper_voice_paths",
                    return_value=(Path("model.onnx"), Path("model.json")),
                ):
                    with mock.patch("pathlib.Path.is_file", return_value=True):
                        with mock.patch(
                            "akki.voice._speak_piper_chunked"
                        ) as chunked:
                            voice.speak_piper("hello", pitch=-12)
        chunked.assert_called_once()
        self.assertEqual(chunked.call_args.args[0], "hello")

    def test_unknown_engine_raises(self) -> None:
        with self.assertRaises(voice.VoiceError):
            voice.speak("hello", engine="bogus")

    def test_capture_push_keeps_audio_when_requested(self) -> None:
        def fake_record(path: Path, **kwargs: object) -> tuple[Path, bool]:
            Path(path).write_bytes(b"RIFF")
            return Path(path), True

        with (
            mock.patch(
                "akki.voice.record_until_silence", side_effect=fake_record
            ),
            mock.patch("akki.voice.transcribe", return_value="hello"),
        ):
            text, kept = voice.capture_push(keep_audio=True)
            self.assertEqual(text, "hello")
            self.assertTrue(kept.exists())
            kept.unlink()

            text, removed = voice.capture_push()
            self.assertEqual(text, "hello")
            self.assertFalse(removed.exists())
