import math
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from akki import speaker
from akki.storage import Storage


class SpeakerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "akki.db")

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def _wav(self, path: Path, frequency: float, seconds: float = 0.2) -> None:
        rate = 16000
        samples = np.sin(
            np.arange(int(seconds * rate)) * (2.0 * math.pi * frequency / rate)
        ).astype("<i2")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(samples.tobytes())

    def test_enroll_and_identify_speaker(self) -> None:
        audio = Path(self.temp.name) / "speaker.wav"
        self._wav(audio, 440.0)
        speaker_id = speaker.enroll_speaker(self.storage, "dev", audio)
        self.assertEqual(speaker_id, 1)
        entries = speaker.list_speakers(self.storage)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "dev")
        self.assertEqual(len(entries[0]["embedding"]), 4)

        info = speaker.identify_speaker(self.storage, audio, threshold=0.7)
        self.assertIsNotNone(info)
        self.assertEqual(info["speaker"], "dev")
        self.assertGreaterEqual(info["similarity"], 0.0)

        self.assertTrue(speaker.forget_speaker(self.storage, "dev"))
        self.assertIsNone(speaker.identify_speaker(self.storage, audio, threshold=0.7))

    def test_speaker_audio_too_short(self) -> None:
        audio = Path(self.temp.name) / "short.wav"
        self._wav(audio, 440.0, seconds=0.01)
        with self.assertRaises(speaker.SpeakerError):
            speaker._embed_audio(audio)


if __name__ == "__main__":
    unittest.main()
