import subprocess
import unittest
from unittest import mock

from akki import shortcut


class DesktopShortcutTests(unittest.TestCase):
    def test_installs_desktop_widget_shortcut(self) -> None:
        with mock.patch.object(
            shortcut.subprocess,
            "run",
            return_value=mock.Mock(
                returncode=0, stdout="C:\\Users\\ankit\\OneDrive\\Desktop\\AKKI Widget.lnk"
            ),
        ) as run:
            result = shortcut.install_desktop_widget_shortcut()
        self.assertTrue(result.ok)
        self.assertEqual(
            result.data["path"], "C:\\Users\\ankit\\OneDrive\\Desktop\\AKKI Widget.lnk"
        )
        self.assertEqual(len(run.call_args.args), 1)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "powershell")
        self.assertIn("-NoProfile", command)
        self.assertIn("-Command", command)

    def test_reports_failure(self) -> None:
        with mock.patch.object(
            shortcut.subprocess,
            "run",
            return_value=mock.Mock(returncode=1, stdout="", stderr="boom"),
        ):
            result = shortcut.install_desktop_widget_shortcut()
        self.assertFalse(result.ok)
        self.assertIn("boom", result.message)


if __name__ == "__main__":
    unittest.main()
