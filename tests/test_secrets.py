import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akki.secrets import SecretsStore


def identity(data: bytes) -> bytes:
    return data


class SecretStoreTests(unittest.TestCase):
    def store(self, path: Path) -> SecretsStore:
        return SecretsStore(path, protect=identity, unprotect=identity)

    def test_set_get_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.json"
            store = self.store(path)
            store.set_secret("AKKI_TEST_SECRET", "hunter2")
            self.assertEqual(store.get_secret("AKKI_TEST_SECRET"), "hunter2")
            self.assertTrue(store.has_secret("AKKI_TEST_SECRET"))
            restored = self.store(path)
            self.assertEqual(restored.get_secret("AKKI_TEST_SECRET"), "hunter2")
            os.environ.pop("AKKI_TEST_SECRET", None)

    def test_delete_removes_secret_and_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.json"
            store = self.store(path)
            store.set_secret("AKKI_TEST_SECRET", "hunter2")
            store.delete_secret("AKKI_TEST_SECRET")
            self.assertIsNone(store.get_secret("AKKI_TEST_SECRET"))
            self.assertNotIn("AKKI_TEST_SECRET", os.environ)
            self.assertFalse(self.store(path).has_secret("AKKI_TEST_SECRET"))

    def test_load_into_env_does_not_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.json"
            store = self.store(path)
            store.set_secret("AKKI_TEST_SECRET", "stored")
            with mock.patch.dict(
                os.environ, {"AKKI_TEST_SECRET": "existing"}, clear=False
            ):
                store.load_into_env()
                self.assertEqual(os.environ["AKKI_TEST_SECRET"], "existing")
            os.environ.pop("AKKI_TEST_SECRET", None)

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "secrets.json"
            store = SecretsStore(path)
            store.set_secret("AKKI_TEST_SECRET", "dpapi-value")
            self.assertEqual(
                SecretsStore(path).get_secret("AKKI_TEST_SECRET"), "dpapi-value"
            )
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("dpapi-value", raw)
            os.environ.pop("AKKI_TEST_SECRET", None)


if __name__ == "__main__":
    unittest.main()
