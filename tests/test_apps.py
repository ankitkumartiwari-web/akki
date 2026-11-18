import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from akki.config import Config
from akki.models import ToolResult
from akki.tools import apps
from akki.tools.apps import _pid_alive


class AppDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        apps._START_APPS_CACHE = None

    def tearDown(self) -> None:
        apps._START_APPS_CACHE = None

    def test_query_start_apps_parses_powershell_json(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout='[{"Name":"Microsoft Store","AppID":"Store_8wekyb3d8bbwe!App"}]',
        )
        with mock.patch.object(apps.subprocess, "run", return_value=completed):
            result = apps._query_start_apps()
        self.assertEqual(
            result,
            [{"name": "Microsoft Store", "app_id": "Store_8wekyb3d8bbwe!App"}],
        )

    def test_discover_apps_caches_results(self) -> None:
        with mock.patch.object(
            apps,
            "_query_start_apps",
            return_value=[{"name": "Notepad", "app_id": "notepad"}],
        ) as query:
            first = apps.discover_apps(refresh=True)
            second = apps.discover_apps()
        self.assertEqual(first, second)
        self.assertEqual(query.call_count, 1)

    def test_find_start_app_prefers_exact_match(self) -> None:
        discovered = [
            {"name": "Microsoft Store", "app_id": "store"},
            {"name": "Store", "app_id": "exact"},
        ]
        with mock.patch.object(apps, "discover_apps", return_value=discovered):
            self.assertEqual(apps.find_start_app("store"), discovered[1])

    def test_list_apps_filters_by_name(self) -> None:
        discovered = [
            {"name": "Microsoft Store", "app_id": "store"},
            {"name": "Notepad", "app_id": "notepad"},
        ]
        with mock.patch.object(apps, "discover_apps", return_value=discovered):
            self.assertEqual(apps.list_apps("store"), discovered[:1])

    def test_launch_app_falls_back_to_start_apps(self) -> None:
        with mock.patch.object(
            apps, "_resolve_executable", return_value=None
        ), mock.patch.object(
            apps, "_start_menu_match", return_value=None
        ), mock.patch.object(
            apps,
            "find_start_app",
            return_value={"name": "Microsoft Store", "app_id": "store"},
        ), mock.patch.object(
            apps, "_launch_aumid", return_value=ToolResult.success("ok")
        ) as launch:
            result = apps.launch_app("store", config=Config())
        self.assertTrue(result.ok)
        launch.assert_called_once_with("Microsoft Store", "store")

    def test_open_in_app_falls_back_to_start_apps(self) -> None:
        with mock.patch.object(apps, "_resolve_target", return_value=Path("C:/tmp/report.txt")), \
             mock.patch.object(apps, "_resolve_executable", return_value=None), \
             mock.patch.object(apps, "find_start_app", return_value={"name": "Microsoft Store", "app_id": "store"}), \
             mock.patch.object(apps, "_launch_aumid", return_value=ToolResult.success("ok")) as launch:
            result = apps.open_in_app("store", "C:/tmp/report.txt", config=Config())
        self.assertTrue(result.ok)
        launch.assert_called_once_with("Microsoft Store", "store", [r"C:\tmp\report.txt"])


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
