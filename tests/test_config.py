import json
import tempfile
import unittest
from pathlib import Path

from odin.config import Config, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_default_apps(self) -> None:
        config = Config.default()
        self.assertIsNotNone(config.find_app("vs code"))
        self.assertIsNotNone(config.find_app("calc"))
        self.assertEqual(config.find_app("vs code")[0], "vscode")

    def test_round_trip(self) -> None:
        config = Config.default()
        config.voice.auto_speak = True
        config.voice.stt_model = "small.en"
        config.voice.stt_language = "hi"
        config.voice.hotkey = "ctrl+alt+space"
        config.voice.hotkey_enabled = True
        config.voice.piper_voice = "en_US-amy-medium"
        config.voice.piper_speaker = 2
        config.voice.tts_engine = "sapi"
        config.llm.cache_ttl_seconds = 120
        restored = Config.from_dict(config.to_dict())
        self.assertEqual(restored.profile, config.profile)
        self.assertEqual(restored.find_app("youtube"), None)
        self.assertEqual(restored.find_app("chrome")[0], "chrome")
        self.assertTrue(restored.voice.auto_speak)
        self.assertEqual(restored.voice.stt_model, "small.en")
        self.assertEqual(restored.voice.stt_language, "hi")
        self.assertEqual(restored.voice.hotkey, "ctrl+alt+space")
        self.assertTrue(restored.voice.hotkey_enabled)
        self.assertEqual(restored.voice.piper_voice, "en_US-amy-medium")
        self.assertEqual(restored.voice.piper_speaker, 2)
        self.assertEqual(restored.voice.tts_engine, "sapi")
        self.assertEqual(restored.llm.cache_ttl_seconds, 120)

    def test_load_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = Config.default()
            config.profile = "guarded"
            save_config(config, path)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["profile"], "guarded")
            loaded = load_config(path)
            self.assertEqual(loaded.profile, "guarded")

    def test_load_creates_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "config.json"
            loaded = load_config(path)
            self.assertTrue(path.exists())
            self.assertIsNotNone(loaded.find_app("notepad"))


if __name__ == "__main__":
    unittest.main()
