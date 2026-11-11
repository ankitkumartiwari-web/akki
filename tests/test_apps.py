import subprocess
import sys
import unittest

from odin.tools.apps import _pid_alive


class ProcessVerificationTests(unittest.TestCase):
    def test_detects_running_and_stopped_process(self) -> None:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(2)"]
        )
        try:
            self.assertTrue(_pid_alive(process.pid))
        finally:
            process.terminate()
            process.wait(timeout=5)
        self.assertFalse(_pid_alive(process.pid))


if __name__ == "__main__":
    unittest.main()
