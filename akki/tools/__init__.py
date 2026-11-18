from .apps import launch_app, list_apps, open_in_app
from .files import find_files, open_path
from .system import (
    change_volume,
    clipboard_read,
    clipboard_write,
    lock_screen,
    take_screenshot,
)
from ..vision import capture_camera, detect_faces
from .web import open_url, read_url, web_search

__all__ = [
    "capture_camera",
    "change_volume",
    "clipboard_read",
    "clipboard_write",
    "detect_faces",
    "find_files",
    "launch_app",
    "list_apps",
    "lock_screen",
    "open_in_app",
    "open_path",
    "open_url",
    "read_url",
    "take_screenshot",
    "web_search",
]
