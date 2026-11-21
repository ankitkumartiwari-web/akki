import unittest
from unittest import mock

from akki.tools.system import clipboard_read, clipboard_write, lock_screen


class LockScreenTests(unittest.TestCase):
    def test_lock_screen_calls_lock_workstation(self) -> None:
        user32 = mock.Mock()
        user32.LockWorkStation.return_value = 1
        with mock.patch("ctypes.WinDLL", return_value=user32):
            result = lock_screen()
        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        user32.LockWorkStation.assert_called_once_with()

    def test_lock_screen_reports_failure(self) -> None:
        user32 = mock.Mock()
        user32.LockWorkStation.return_value = 0
        with mock.patch("ctypes.WinDLL", return_value=user32):
            with mock.patch("ctypes.get_last_error", return_value=5):
                result = lock_screen()
        self.assertFalse(result.ok)
        self.assertIn("5", result.message)


class ClipboardTests(unittest.TestCase):
    def test_clipboard_write_pipes_text(self) -> None:
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch("akki.tools.system._run_powershell", return_value=completed) as run:
            result = clipboard_write("hello")
        self.assertTrue(result.ok)
        self.assertEqual(run.call_args.kwargs["stdin"], "hello")

    def test_clipboard_read_uses_get_clipboard(self) -> None:
        completed = mock.Mock(returncode=0, stdout="hello", stderr="")
        with mock.patch("akki.tools.system._run_powershell", return_value=completed) as run:
            result = clipboard_read()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["text"], "hello")
        self.assertIn("Get-Clipboard", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
