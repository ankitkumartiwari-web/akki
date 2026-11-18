from __future__ import annotations

import threading
from collections.abc import Callable


class TrayError(RuntimeError):
    pass


def tray_supported() -> bool:
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


class TrayIcon:
    def __init__(
        self,
        on_settings: Callable[[], None],
        *,
        on_widget: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        title: str = "AKKI",
    ) -> None:
        self.on_settings = on_settings
        self.on_widget = on_widget
        self.on_quit = on_quit
        self.title = title
        self._icon: object | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.active:
            return
        if not tray_supported():
            raise TrayError(
                "tray support needs pystray and pillow: "
                "pip install -e .[desktop]"
            )
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (64, 64), "#0b1220")
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill="#1d4ed8", outline="#6ee7ff", width=3)
        draw.text((24, 18), "O", fill="#ffffff")
        items = [
            pystray.MenuItem(
                "Settings", lambda icon, item: self.on_settings(), default=True
            )
        ]
        if self.on_widget is not None:
            items.append(
                pystray.MenuItem(
                    "Desktop widget",
                    lambda icon, item: self.on_widget(),
                )
            )
        items.append(
            pystray.MenuItem("Quit tray", lambda icon, item: self._quit())
        )
        menu = pystray.Menu(*items)
        icon = pystray.Icon("akki", image, self.title, menu)
        self._icon = icon
        self._thread = threading.Thread(
            target=icon.run, name="akki-tray", daemon=True
        )
        self._thread.start()

    def _quit(self) -> None:
        self.stop()
        if self.on_quit is not None:
            self.on_quit()

    def stop(self) -> None:
        icon = self._icon
        self._icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
