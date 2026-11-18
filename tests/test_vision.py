import tempfile
import unittest
from pathlib import Path

from akki import vision
from akki.storage import Storage


class VisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "akki.db")

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_capture_camera_unavailable(self) -> None:
        result = vision.capture_camera()
        self.assertFalse(result.ok)
        self.assertIn("opencv-python", result.message)

    def test_vision_face_helpers_use_storage(self) -> None:
        face_id = vision.enroll_face(self.storage, "dev", "Zm9vYmFy")
        self.assertEqual(face_id, 1)
        entries = vision.list_faces(self.storage)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "dev")
        self.assertTrue(vision.forget_face(self.storage, "dev"))


if __name__ == "__main__":
    unittest.main()
