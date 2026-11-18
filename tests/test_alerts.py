import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from akki import alerts
from akki.config import AlertSettings, Config
from akki.llm import FallbackOutcome
from akki.models import ToolResult
from akki.storage import Storage


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"{}"


class FakeMail:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.logged_out = False

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        return "OK", [b"logged in"]

    def select(self, folder: str) -> tuple[str, list[bytes]]:
        return "OK", [b"1"]

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch":
            return "OK", [(b"1 (BODY[] {1}", self.raw)]
        return "OK", [b""]

    def logout(self) -> None:
        self.logged_out = True


class AlertTests(unittest.TestCase):
    def test_send_ntfy_posts_json_payload(self) -> None:
        settings = AlertSettings(ntfy_topic="my-topic")
        with mock.patch.object(
            alerts, "urlopen", return_value=FakeResponse()
        ) as urlopen:
            result = alerts.send_ntfy(settings, "Hello", "Important message")
        self.assertTrue(result.ok)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["topic"], "my-topic")
        self.assertEqual(payload["title"], "Hello")
        self.assertEqual(payload["message"], "Important message")

    def test_send_ntfy_requires_topic(self) -> None:
        result = alerts.send_ntfy(AlertSettings(), "Hello", "Body")
        self.assertFalse(result.ok)

    def test_fetch_unseen_mail_parses_message(self) -> None:
        raw = (
            b"From: Alice <alice@example.com>\r\n"
            b"Subject: Invoice due\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Please pay the invoice today."
        )
        fake = FakeMail(raw)
        settings = AlertSettings(
            imap_host="imap.example.com",
            imap_user="user@example.com",
            imap_password_env="AKKI_TEST_IMAP_PASSWORD",
        )
        with mock.patch.dict(
            os.environ, {"AKKI_TEST_IMAP_PASSWORD": "secret"}, clear=False
        ), mock.patch.object(
            alerts.imaplib, "IMAP4_SSL", return_value=fake
        ):
            messages = alerts.fetch_unseen_mail(settings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["subject"], "Invoice due")
        self.assertIn("alice@example.com", messages[0]["from"])
        self.assertIn("Please pay", messages[0]["snippet"])
        self.assertTrue(fake.logged_out)

    def test_fetch_unseen_mail_requires_password(self) -> None:
        settings = AlertSettings(
            imap_host="imap.example.com",
            imap_user="user@example.com",
            imap_password_env="AKKI_TEST_MISSING_PASSWORD",
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(alerts.AlertError):
                alerts.fetch_unseen_mail(settings)

    def test_score_importance_uses_llm_number(self) -> None:
        with mock.patch.object(
            alerts, "ask_plain", return_value=FallbackOutcome(text="0.9")
        ):
            score = alerts.score_importance(
                {"subject": "Hello", "from": "a@b.c", "snippet": "Body"}, Config()
            )
        self.assertAlmostEqual(score, 0.9)

    def test_score_importance_falls_back_to_keywords(self) -> None:
        with mock.patch.object(
            alerts, "ask_plain", return_value=FallbackOutcome(error="offline")
        ):
            score = alerts.score_importance(
                {"subject": "Your OTP code", "from": "a@b.c", "snippet": "123456"},
                Config(),
            )
        self.assertGreaterEqual(score, 0.9)

    def test_poll_once_sends_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            storage = Storage(Path(raw_dir) / "test.db")
            config = Config()
            config.alerts = AlertSettings(
                enabled=True,
                ntfy_topic="topic",
                imap_host="imap.example.com",
                imap_user="user@example.com",
                importance_threshold=0.6,
            )
            item = {
                "uid": "1",
                "from": "Boss <boss@example.com>",
                "subject": "Urgent deadline",
                "date": "",
                "snippet": "Please respond now.",
            }
            try:
                with mock.patch.object(
                    alerts, "fetch_unseen_mail", return_value=[item]
                ), mock.patch.object(
                    alerts, "score_importance", return_value=0.9
                ), mock.patch.object(
                    alerts,
                    "send_ntfy",
                    return_value=ToolResult.success("sent"),
                ) as send:
                    first = alerts.poll_once(storage, config)
                    second = alerts.poll_once(storage, config)
                self.assertEqual(len(first), 1)
                self.assertEqual(second, [])
                self.assertEqual(send.call_count, 1)
            finally:
                storage.close()

    def test_poll_once_records_low_importance_without_sending(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            storage = Storage(Path(raw_dir) / "test.db")
            config = Config()
            config.alerts = AlertSettings(
                enabled=True,
                ntfy_topic="topic",
                imap_host="imap.example.com",
                imap_user="user@example.com",
                importance_threshold=0.6,
            )
            item = {
                "uid": "2",
                "from": "News <news@example.com>",
                "subject": "Daily digest",
                "date": "",
                "snippet": "Nothing urgent.",
            }
            try:
                with mock.patch.object(
                    alerts, "fetch_unseen_mail", return_value=[item]
                ), mock.patch.object(
                    alerts, "score_importance", return_value=0.2
                ), mock.patch.object(
                    alerts, "send_ntfy"
                ) as send:
                    first = alerts.poll_once(storage, config)
                    second = alerts.poll_once(storage, config)
                self.assertEqual(first, [])
                self.assertEqual(second, [])
                send.assert_not_called()
                self.assertTrue(storage.alert_seen("imap", "user@example.com:INBOX:2"))
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
