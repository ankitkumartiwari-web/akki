import tempfile
import time
import unittest
from pathlib import Path

from akki import scheduler
from akki.storage import Storage


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "akki.db")

    def tearDown(self) -> None:
        self.storage.close()
        self.temp.cleanup()

    def test_schedule_and_cancel(self) -> None:
        job_id = scheduler.schedule_every(self.storage, "open notepad", 3600)
        jobs = scheduler.list_jobs(self.storage)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["command"], "open notepad")
        self.assertTrue(scheduler.cancel_job(self.storage, job_id))

    def test_due_jobs_pop_once(self) -> None:
        scheduler.schedule_every(self.storage, "open notepad", 3600)
        self.assertEqual(scheduler.due_jobs(self.storage, time.time() + 10), [])
        self.storage.add_job(
            command="open notepad",
            kind="interval",
            interval_seconds=3600,
            daily_time=None,
            next_run=time.time() - 1,
        )
        due = scheduler.due_jobs(self.storage, time.time())
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["command"], "open notepad")

    def test_one_shot_job_is_removed_after_running(self) -> None:
        scheduler.schedule_once(self.storage, "__reminder__: drink water", 1)
        due = scheduler.due_jobs(self.storage, time.time() + 2)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["command"], "__reminder__: drink water")
        self.assertEqual(scheduler.due_jobs(self.storage, time.time() + 10), [])


if __name__ == "__main__":
    unittest.main()
