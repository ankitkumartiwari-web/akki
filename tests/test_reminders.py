import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from akki import scheduler
from akki.cli import build_registry, handle
from akki.config import Config
from akki.conversation import Conversation
from akki.models import ToolResult
from akki.reminders import format_duration, parse_reminder
from akki.router import route
from akki.storage import Storage
from akki.tools.reminders import announce_reminder


class ReminderParseTests(unittest.TestCase):
    def test_parses_english_reminder(self) -> None:
        self.assertEqual(
            parse_reminder("remind me in 10 minutes to stretch"),
            (600, "stretch"),
        )
        self.assertEqual(
            parse_reminder("remind me to call mom in 2 hours"),
            (7200, "call mom"),
        )
        self.assertEqual(
            parse_reminder("set a timer for 5 minutes to tea"),
            (300, "tea"),
        )

    def test_parses_hinglish_reminder(self) -> None:
        self.assertEqual(
            parse_reminder("mujhe 10 minute baad yaad dilana ki pani peena hai"),
            (600, "pani peena hai"),
        )
        self.assertEqual(
            parse_reminder("10 minute baad yaad dilana pani peena"),
            (600, "pani peena"),
        )

    def test_ignores_non_reminder_sentences(self) -> None:
        self.assertIsNone(parse_reminder("search for 5 minutes tutorial"))
        self.assertIsNone(parse_reminder("remind me to call mom"))
        self.assertIsNone(parse_reminder("remind me in 10 minutes"))

    def test_formats_duration(self) -> None:
        self.assertEqual(format_duration(1), "1 second")
        self.assertEqual(format_duration(600), "10 minutes")
        self.assertEqual(format_duration(7200), "2 hours")


class ReminderHandleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "akki.db")
        self.config = Config.default()
        self.config.llm.local_enabled = False
        self.registry = build_registry(self.config, self.storage)

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_handle_schedules_one_shot_reminder(self) -> None:
        result = handle(
            "remind me in 10 minutes to stretch",
            self.config,
            self.registry,
            Conversation(),
            self.storage,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["seconds"], 600)
        jobs = scheduler.list_jobs(self.storage)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["command"], "__reminder__: stretch")
        self.assertEqual(jobs[0]["kind"], "once")

    def test_due_reminder_executes_and_speaks(self) -> None:
        scheduler.schedule_once(
            self.storage, "__reminder__: drink water", 1
        )
        with mock.patch("akki.cli.speak_text") as speak:
            results = scheduler.execute_due(
                self.storage, self.registry, self.config, time.time() + 2
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1].message, "Reminder: drink water")
        speak.assert_called_once_with("Reminder: drink water", self.config)

    def test_internal_reminder_prefix_routes_to_tool(self) -> None:
        request = route("__reminder__: drink water")
        self.assertIsNotNone(request)
        self.assertEqual(request.tool, "reminder")
        self.assertEqual(request.args["text"], "drink water")

    def test_announce_reminder_speaks(self) -> None:
        with mock.patch("akki.cli.speak_text") as speak:
            result = announce_reminder("drink water", config=self.config)
        self.assertEqual(result.message, "Reminder: drink water")
        self.assertEqual(result.data["channel"], "voice")
        speak.assert_called_once_with("Reminder: drink water", self.config)

    def test_announce_reminder_falls_back_to_mobile(self) -> None:
        with mock.patch("akki.cli.speak_text", side_effect=RuntimeError("no audio")):
            with mock.patch(
                "akki.tools.reminders.alerts.send_mobile_alert",
                return_value=ToolResult.success("sent"),
            ) as alert:
                result = announce_reminder("drink water", config=self.config)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["channel"], "mobile")
        alert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
