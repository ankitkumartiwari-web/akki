import json
import tempfile
import unittest
from pathlib import Path

from akki.config import (
    AlertSettings,
    Config,
    DesktopSettings,
    MCPServerSettings,
    apply_config,
    load_config,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_default_apps(self) -> None:
        config = Config.default()
        self.assertIsNotNone(config.find_app("vs code"))
        self.assertIsNotNone(config.find_app("calc"))
        self.assertEqual(config.find_app("vs code")[0], "vscode")
        self.assertTrue(config.voice.wake_enabled)

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
        config.voice.edge_voice = "en-IN-NeerjaNeural"
        config.voice.nsfw_edge_voice = "en-IN-PrabhatNeural"
        config.voice.hindi_edge_voice = "hi-IN-MadhurNeural"
        config.voice.nsfw_hindi_edge_voice = "hi-IN-SwaraNeural"
        config.voice.tts_pitch = -25
        config.llm.cache_ttl_seconds = 120
        config.web.enabled = True
        config.web.port = 9999
        config.alerts = AlertSettings(
            enabled=True,
            ntfy_topic="test-topic",
            imap_host="imap.example.com",
            imap_user="user@example.com",
            importance_threshold=0.7,
        )
        config.desktop = DesktopSettings(
            tray_enabled=True, widget_enabled=True, bubble_enabled=False
        )
        config.mcp_servers["fake"] = MCPServerSettings(
            command=["python", "fake.py"],
            env={"FAKE": "1"},
            timeout_seconds=3,
        )
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
        self.assertEqual(restored.voice.edge_voice, "en-IN-NeerjaNeural")
        self.assertEqual(restored.voice.nsfw_edge_voice, "en-IN-PrabhatNeural")
        self.assertEqual(restored.voice.hindi_edge_voice, "hi-IN-MadhurNeural")
        self.assertEqual(
            restored.voice.nsfw_hindi_edge_voice, "hi-IN-SwaraNeural"
        )
        self.assertEqual(restored.voice.tts_pitch, -25)
        self.assertEqual(restored.llm.cache_ttl_seconds, 120)
        self.assertTrue(restored.web.enabled)
        self.assertEqual(restored.web.port, 9999)
        self.assertTrue(restored.alerts.enabled)
        self.assertEqual(restored.alerts.ntfy_topic, "test-topic")
        self.assertEqual(restored.alerts.imap_host, "imap.example.com")
        self.assertEqual(restored.alerts.importance_threshold, 0.7)
        self.assertTrue(restored.desktop.tray_enabled)
        self.assertTrue(restored.desktop.widget_enabled)
        self.assertFalse(restored.desktop.bubble_enabled)
        self.assertEqual(restored.mcp_servers["fake"].command, ["python", "fake.py"])
        self.assertEqual(restored.mcp_servers["fake"].env, {"FAKE": "1"})
        self.assertEqual(restored.mcp_servers["fake"].timeout_seconds, 3)

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

    def test_apply_config_updates_same_object(self) -> None:
        target = Config.default()
        source = Config.default()
        source.profile = "nsfw"
        source.web.port = 1234
        source.desktop.bubble_enabled = False
        apply_config(target, source)
        self.assertEqual(target.profile, "nsfw")
        self.assertEqual(target.web.port, 1234)
        self.assertFalse(target.desktop.bubble_enabled)

    def test_load_creates_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "config.json"
            loaded = load_config(path)
            self.assertTrue(path.exists())
            self.assertIsNotNone(loaded.find_app("notepad"))


if __name__ == "__main__":
    unittest.main()
