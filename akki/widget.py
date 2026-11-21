from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

from .config import Config, config_path, save_config
from .llm import resolve_endpoint
from .models import ToolResult
from .secrets import SecretError, SecretsStore

PROFILE_VALUES = ("sovereign", "nsfw", "guarded")
PROFILE_LABELS = {"sovereign": "Sovereign", "nsfw": "NSFW", "guarded": "Guarded"}

WIDTH = 480
HEIGHT = 764
PAD = 24
CARD_L = 20
CARD_R = WIDTH - 20
INNER_L = 40
INNER_R = CARD_R - 20

SURFACE = "#111419"
SURFACE_CONTAINER = "#181C23"
SURFACE_HIGH = "#20252E"
FIELD = "#222833"
FIELD_HOVER = "#2A303B"
OUTLINE = "#343B47"
HYPERLINK = "#8ADFD0"
TEXT = "#E7EAF2"
TEXT_VARIANT = "#AEB6C4"
TEXT_MUTED = "#747C89"
PRIMARY = "#8ADFD0"
ON_PRIMARY = "#073029"
PRIMARY_DIM = "#1A3B36"
SECONDARY = "#C9C3DC"
SUCCESS = "#8EE3B4"
ERROR = "#FFB4AB"


def _shade(color: str, factor: float) -> str:
    color = color.lstrip("#")
    channels = [int(color[i : i + 2], 16) for i in (0, 2, 4)]
    if factor >= 0:
        channels = [int(c + (255 - c) * factor) for c in channels]
    else:
        channels = [int(c * (1 + factor)) for c in channels]
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in channels)


def _enable_dpi_awareness() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _apply_window_chrome(root: object) -> None:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        wid = root.winfo_id()
        hwnd = user32.GetAncestor(wid, 2) or user32.GetParent(wid) or wid

        def attribute(name: int, value: int) -> None:
            data = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, name, ctypes.byref(data), ctypes.sizeof(data)
            )

        def colorref(hex_color: str) -> int:
            value = hex_color.lstrip("#")
            red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
            return blue << 16 | green << 8 | red

        attribute(20, 1)
        attribute(19, 1)
        attribute(33, 2)
        attribute(34, colorref(OUTLINE))
        attribute(35, colorref(SURFACE))
        attribute(36, colorref(TEXT))
    except Exception:
        pass


def _work_area(root: object) -> tuple[int, int]:
    try:
        import ctypes

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = Rect()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        if rect.right > 200 and rect.bottom > 200:
            return rect.right, rect.bottom
    except Exception:
        pass
    return root.winfo_screenwidth(), root.winfo_screenheight()


def _backdrop(width: int, height: int) -> object:
    from PIL import Image, ImageTk

    img = Image.new("RGB", (width, height), (17, 20, 25))
    grain = Image.effect_noise((width, height), 5).convert("L")
    grain = Image.merge(
        "RGBA", (grain, grain, grain, Image.new("L", (width, height), 6))
    )
    img = Image.alpha_composite(img.convert("RGBA"), grain)
    return ImageTk.PhotoImage(img)


def _rounded(canvas: object, x1, y1, x2, y2, radius, **kwargs) -> int:
    import math

    r = max(0.0, min(float(radius), (x2 - x1) / 2, (y2 - y1) / 2))
    steps = 10
    corners = (
        (x2 - r, y1 + r, -90, 0),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
        (x1 + r, y1 + r, 180, 270),
    )
    points: list[float] = []
    for cx, cy, start, end in corners:
        for step in range(steps + 1):
            angle = math.radians(start + (end - start) * step / steps)
            points.extend((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return canvas.create_polygon(points, smooth=False, **kwargs)


class _TextButton:
    def __init__(
        self,
        canvas: object,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        command: Callable[[], None],
        *,
        variant: str = "text",
        font: tuple = ("Segoe UI", 10, "bold"),
    ) -> None:
        self.canvas = canvas
        self.command = command
        self.variant = variant
        self.width = width
        self.height = height
        self.base = {
            "filled": PRIMARY,
            "tonal": PRIMARY_DIM,
            "outlined": SURFACE_HIGH,
            "text": SURFACE_CONTAINER,
        }[variant]
        self.foreground = {
            "filled": ON_PRIMARY,
            "tonal": PRIMARY,
            "outlined": TEXT,
            "text": TEXT_VARIANT,
        }[variant]
        self.box = _rounded(
            canvas,
            x,
            y,
            x + width,
            y + height,
            height // 2,
            fill=self.base,
            outline=OUTLINE if variant == "outlined" else "",
            width=1,
        )
        if variant == "text":
            canvas.itemconfigure(self.box, outline="")
        self.label = canvas.create_text(
            x + width / 2,
            y + height / 2,
            text=text,
            fill=self.foreground,
            font=font,
        )
        for item in (self.box, self.label):
            canvas.tag_bind(item, "<Enter>", self._enter)
            canvas.tag_bind(item, "<Leave>", self._leave)
            canvas.tag_bind(item, "<Button-1>", self._press)
            canvas.tag_bind(item, "<ButtonRelease-1>", self._release)
        self._hover = False

    def _fill(self, hover: bool) -> str:
        if self.variant == "text":
            return _shade(SURFACE_CONTAINER, 0.08) if hover else ""
        return _shade(self.base, 0.08 if hover else 0.0)

    def _enter(self, _event=None) -> None:
        self._hover = True
        self.canvas.itemconfigure(self.box, fill=self._fill(True))
        if self.variant == "text":
            self.canvas.itemconfigure(self.label, fill=PRIMARY)
        self.canvas.configure(cursor="hand2")

    def _leave(self, _event=None) -> None:
        self._hover = False
        self.canvas.itemconfigure(self.box, fill=self._fill(False))
        self.canvas.itemconfigure(self.label, fill=self.foreground)
        self.canvas.configure(cursor="")

    def _press(self, _event=None) -> None:
        self.canvas.itemconfigure(
            self.box,
            fill=(
                _shade(SURFACE_CONTAINER, 0.10)
                if self.variant == "text"
                else _shade(self.base, 0.10)
            ),
        )

    def _release(self, event=None) -> None:
        self.canvas.itemconfigure(self.box, fill=self._fill(self._hover))
        if event is None or self._inside(event):
            self.command()

    def _inside(self, event) -> bool:
        coords = self.canvas.coords(self.box)
        if not coords:
            return True
        xs = coords[0::2]
        ys = coords[1::2]
        return min(xs) <= event.x <= max(xs) and min(ys) <= event.y <= max(ys)


class _Switch:
    def __init__(
        self,
        canvas: object,
        x: int,
        y: int,
        variable: object,
        command: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.variable = variable
        self.command = command
        self.x = x
        self.y = y
        self.w = 46
        self.h = 26
        self.track = _rounded(
            canvas,
            x,
            y,
            x + self.w,
            y + self.h,
            self.h // 2,
            fill=FIELD_HOVER,
            outline="",
        )
        self.knob = canvas.create_oval(
            x + 3,
            y + 3,
            x + 3 + 20,
            y + 3 + 20,
            fill=TEXT_MUTED,
            outline="",
        )
        for item in (self.track, self.knob):
            canvas.tag_bind(item, "<Button-1>", self._toggle)
            canvas.tag_bind(item, "<Enter>", lambda _e: canvas.configure(cursor="hand2"))
            canvas.tag_bind(item, "<Leave>", lambda _e: canvas.configure(cursor=""))
        self._render()

    def _toggle(self, _event=None) -> None:
        self.variable.set(not bool(self.variable.get()))
        self._render()
        if self.command is not None:
            self.command()

    def _render(self) -> None:
        on = bool(self.variable.get())
        self.canvas.itemconfigure(
            self.track, fill=PRIMARY if on else FIELD_HOVER
        )
        self.canvas.coords(
            self.knob,
            self.x + (self.w - 23 if on else 3),
            self.y + 3,
            self.x + (self.w - 23 if on else 3) + 20,
            self.y + 23,
        )
        self.canvas.itemconfigure(self.knob, fill=ON_PRIMARY if on else TEXT_VARIANT)


class _Segmented:
    def __init__(
        self,
        canvas: object,
        x: int,
        y: int,
        width: int,
        height: int,
        values: tuple[str, ...],
        variable: object,
    ) -> None:
        self.canvas = canvas
        self.variable = variable
        self.values = values
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.gap = 4
        self.cell = (width - self.gap * (len(values) - 1)) / len(values)
        _rounded(
            canvas,
            x,
            y,
            x + width,
            y + height,
            height // 2,
            fill="#141821",
            outline=OUTLINE,
            width=1,
        )
        self.pill = _rounded(
            canvas,
            x + 4,
            y + 4,
            x + 4 + self.cell,
            y + height - 4,
            (height - 8) // 2,
            fill=PRIMARY_DIM,
            outline="",
        )
        self.base_texts = [
            PROFILE_LABELS.get(value, value.capitalize()) for value in values
        ]
        self.labels = []
        for index, value in enumerate(values):
            cx = x + index * (self.cell + self.gap) + self.cell / 2
            label = canvas.create_text(
                cx,
                y + height / 2,
                text=self.base_texts[index],
                fill=TEXT_VARIANT,
                font=("Segoe UI", 10, "bold"),
            )
            self.labels.append(label)
            hit = canvas.create_rectangle(
                x + index * (self.cell + self.gap),
                y,
                x + index * (self.cell + self.gap) + self.cell,
                y + height,
                fill="",
                outline="",
            )
            canvas.tag_bind(hit, "<Button-1>", lambda _e, i=index: self._select(i))
            canvas.tag_bind(
                hit,
                "<Enter>",
                lambda _e, i=index: self._hover(i, True),
            )
            canvas.tag_bind(
                hit,
                "<Leave>",
                lambda _e, i=index: self._hover(i, False),
            )
        self._sync()

    def _hover(self, index: int, active: bool) -> None:
        self.canvas.configure(cursor="hand2" if active else "")
        try:
            selected = self.values.index(str(self.variable.get()))
        except ValueError:
            selected = 0
        fill = TEXT if active and index != selected else (
            PRIMARY if index == selected else TEXT_VARIANT
        )
        self.canvas.itemconfigure(self.labels[index], fill=fill)

    def _select(self, index: int) -> None:
        self.variable.set(self.values[index])
        self._sync()

    def _sync(self) -> None:
        try:
            index = self.values.index(str(self.variable.get()))
        except ValueError:
            index = 0
        self.canvas.delete(self.pill)
        self.pill = _rounded(
            self.canvas,
            self.x + 4 + index * (self.cell + self.gap),
            self.y + 4,
            self.x + 4 + index * (self.cell + self.gap) + self.cell,
            self.y + self.height - 4,
            (self.height - 8) // 2,
            fill=PRIMARY_DIM,
            outline="",
        )
        self.canvas.tag_lower(self.pill, self.labels[0])
        for i, label in enumerate(self.labels):
            text = ("\u2713  " if i == index else "") + self.base_texts[i]
            self.canvas.itemconfigure(
                label,
                text=text,
                fill=PRIMARY if i == index else TEXT_VARIANT,
            )


class DesktopWidget:
    def __init__(
        self,
        config: Config,
        *,
        secrets: SecretsStore,
        config_file: Path | None = None,
        on_save: Callable[[Config], None] | None = None,
        on_listen: Callable[[], None] | None = None,
        on_open_settings: Callable[[], None] | None = None,
        on_test_alert: Callable[[], ToolResult] | None = None,
    ) -> None:
        self.config = config
        self.secrets = secrets
        self.config_file = config_file or config_path()
        self.on_save = on_save
        self.on_listen = on_listen
        self.on_open_settings = on_open_settings
        self.on_test_alert = on_test_alert
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue[str] = queue.Queue()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.active:
            return
        self._thread = threading.Thread(
            target=self._run, name="akki-desktop-widget", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self.active:
            self._queue.put("stop")

    def _run(self) -> None:
        import tkinter as tk
        import tkinter.font as tkfont
        from tkinter import messagebox

        _enable_dpi_awareness()
        root = tk.Tk()
        root.title("AKKI")
        root.minsize(WIDTH, HEIGHT)
        root.geometry(f"{WIDTH}x{HEIGHT}")
        root.configure(bg=SURFACE)
        root.attributes("-topmost", True)
        _apply_window_chrome(root)

        families = set(tkfont.families(root))
        display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else "Segoe UI"
        body = "Segoe UI Variable Text" if "Segoe UI Variable Text" in families else "Segoe UI"

        canvas = tk.Canvas(
            root,
            width=WIDTH,
            height=HEIGHT,
            bg=SURFACE,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(fill="both", expand=True)
        photo = _backdrop(WIDTH, HEIGHT)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.photo = photo

        def section(x1, y1, x2, y2, radius=26, fill=SURFACE_CONTAINER) -> int:
            return _rounded(
                canvas,
                x1,
                y1,
                x2,
                y2,
                radius,
                fill=fill,
                outline="#2A313C",
                width=1,
            )

        def label(x, y, text, *, size=10, bold=False, color=TEXT_VARIANT, anchor="w", family=None):
            font = (family or body, size, "bold" if bold else "normal")
            return canvas.create_text(
                x,
                y,
                text=text,
                fill=color,
                font=font,
                anchor=anchor,
            )

        def field(x, y, width, height=32) -> object:
            _rounded(
                canvas,
                x,
                y,
                x + width,
                y + height,
                14,
                fill=FIELD,
                outline="#2C3340",
                width=1,
            )
            entry = tk.Entry(
                root,
                relief="flat",
                bd=0,
                bg=FIELD,
                fg=TEXT,
                insertbackground=PRIMARY,
                font=(body, 10),
                highlightthickness=0,
            )
            canvas.create_window(
                x + 12,
                y + height / 2,
                window=entry,
                anchor="w",
                width=width - 24,
                height=height - 10,
            )
            return entry

        def toast(message: str) -> None:
            original = canvas.itemcget(status_text, "text")
            canvas.itemconfigure(status_text, text=message, fill=PRIMARY)
            canvas.itemconfigure(status_dot, fill=PRIMARY)

            def restore() -> None:
                if not root.winfo_exists():
                    return
                canvas.itemconfigure(status_text, text=original, fill=SUCCESS)
                canvas.itemconfigure(status_dot, fill=SUCCESS)

            root.after(2200, restore)

        # Header ------------------------------------------------------------
        _rounded(canvas, PAD, 24, PAD + 34, 58, 17, fill=PRIMARY_DIM, outline="#31625A", width=1)
        _rounded(canvas, PAD + 6, 30, PAD + 28, 52, 11, fill=PRIMARY, outline="", width=0)
        canvas.create_text(
            PAD + 17,
            41,
            text="A",
            fill=ON_PRIMARY,
            font=(display, 13, "bold"),
        )
        label(PAD + 46, 28, "AKKI", size=20, bold=True, color=TEXT, family=display)
        label(PAD + 47, 52, "your private desktop copilot", size=9, color=TEXT_MUTED)

        status_pill = _rounded(
            canvas,
            WIDTH - PAD - 92,
            28,
            WIDTH - PAD,
            56,
            14,
            fill="#18231F",
            outline="#2F4642",
            width=1,
        )
        status_dot = canvas.create_oval(
            WIDTH - PAD - 78, 38, WIDTH - PAD - 68, 48, fill=SUCCESS, outline=""
        )
        status_text = canvas.create_text(
            WIDTH - PAD - 60,
            42,
            text="Ready",
            fill=SUCCESS,
            font=(body, 8, "bold"),
            anchor="w",
        )

        # Mode --------------------------------------------------------------
        section(CARD_L, 84, CARD_R, 188)
        label(INNER_L, 104, "MODE", size=8, bold=True, color=TEXT_MUTED)
        mode_var = tk.StringVar(value=self.config.profile)
        modes = _Segmented(canvas, INNER_L, 126, INNER_R - INNER_L, 44, PROFILE_VALUES, mode_var)

        # Alerts ------------------------------------------------------------
        section(CARD_L, 196, CARD_R, 260)
        label(INNER_L, 214, "Mobile alerts", size=10, bold=True, color=TEXT)
        alert_status = canvas.create_text(
            INNER_R,
            214,
            text="",
            fill=TEXT_VARIANT,
            font=(body, 9),
            anchor="e",
        )
        label(INNER_L, 238, "Email + ntfy push, handled locally", size=8, color=TEXT_MUTED)
        # Secrets -----------------------------------------------------------
        section(CARD_L, 268, CARD_R, 528)
        label(INNER_L, 288, "Passwords & tokens", size=11, bold=True, color=TEXT)
        label(INNER_R, 288, "Windows Credential Manager", size=8, color=TEXT_MUTED, anchor="e")

        imap_env = self.config.alerts.imap_password_env or "AKKI_IMAP_PASSWORD"
        ntfy_env = self.config.alerts.ntfy_token_env or "AKKI_NTFY_TOKEN"
        cloud_env = (
            resolve_endpoint(self.config.llm)[2]
            or self.config.llm.api_key_env
            or "OPENROUTER_API_KEY"
        )

        password_vars: dict[str, tk.StringVar] = {}
        password_entries: list[object] = []
        secret_status: dict[str, object] = {}

        def add_secret(row_y: int, label_text: str, env_name: str) -> None:
            variable = tk.StringVar()
            password_vars[env_name] = variable
            label(INNER_L, row_y, label_text, size=9, bold=True, color=TEXT_VARIANT)
            status = label(INNER_R, row_y, "", size=8, color=TEXT_MUTED, anchor="e")
            secret_status[env_name] = status
            entry = field(INNER_L, row_y + 12, INNER_R - INNER_L, 34)
            entry.configure(textvariable=variable, show="•")
            password_entries.append(entry)

        add_secret(318, "IMAP password", imap_env)
        add_secret(384, "ntfy token", ntfy_env)
        add_secret(450, "Cloud API key", cloud_env)

        # Toggles -----------------------------------------------------------
        section(CARD_L, 536, CARD_R, 668)
        show_passwords = tk.BooleanVar(value=False)

        def toggle_passwords() -> None:
            mask = "" if show_passwords.get() else "•"
            for entry in password_entries:
                entry.configure(show=mask)

        _Switch(canvas, INNER_R - 46, 548, show_passwords, toggle_passwords)
        label(INNER_L, 561, "Show passwords", size=10, color=TEXT)
        canvas.create_line(INNER_L, 580, INNER_R, 580, fill="#222833")

        start_with_akki = tk.BooleanVar(value=self.config.desktop.widget_enabled)
        _Switch(canvas, INNER_R - 46, 590, start_with_akki)
        label(INNER_L, 603, "Start this widget with AKKI", size=10, color=TEXT)
        canvas.create_line(INNER_L, 622, INNER_R, 622, fill="#222833")

        pin_var = tk.BooleanVar(value=True)

        def toggle_pin() -> None:
            root.attributes("-topmost", bool(pin_var.get()))

        _Switch(canvas, INNER_R - 46, 632, pin_var, toggle_pin)
        label(INNER_L, 645, "Always on top", size=10, color=TEXT)

        # Actions -----------------------------------------------------------
        def refresh_status() -> None:
            alerts_on = "On" if self.config.alerts.enabled else "Off"
            host = self.config.alerts.imap_host or "not configured"
            canvas.itemconfigure(
                alert_status, text=f"{alerts_on} · {host}"
            )
            for env_name, item in secret_status.items():
                saved = self.secrets.has_secret(env_name)
                canvas.itemconfigure(
                    item,
                    text="saved" if saved else "not saved",
                    fill=SUCCESS if saved else TEXT_MUTED,
                )

        def save_entered_secrets() -> None:
            for env_name, variable in password_vars.items():
                value = variable.get()
                if value:
                    self.secrets.set_secret(env_name, value)
                    variable.set("")

        def save() -> None:
            try:
                new = Config.from_dict(self.config.to_dict())
                new.profile = mode_var.get()
                new.desktop.widget_enabled = bool(start_with_akki.get())
                save_config(new, self.config_file)
                save_entered_secrets()
                self.config = new
                if self.on_save is not None:
                    self.on_save(new)
                refresh_status()
            except (OSError, SecretError, ValueError) as exc:
                messagebox.showerror("AKKI", str(exc), parent=root)
                return
            toast("Saved")

        def clear_saved() -> None:
            if not messagebox.askyesno(
                "AKKI",
                "Delete all passwords and tokens saved by AKKI?",
                parent=root,
            ):
                return
            try:
                for env_name in password_vars:
                    self.secrets.delete_secret(env_name)
                for variable in password_vars.values():
                    variable.set("")
            except (OSError, SecretError) as exc:
                messagebox.showerror("AKKI", str(exc), parent=root)
                return
            refresh_status()

        def test_alert() -> None:
            if self.on_test_alert is None:
                return
            try:
                save_entered_secrets()
            except (OSError, SecretError) as exc:
                messagebox.showerror("AKKI", str(exc), parent=root)
                return
            refresh_status()
            result = self.on_test_alert()
            if result.ok:
                toast("Alert sent")
            else:
                messagebox.showerror("AKKI", result.message, parent=root)

        def talk() -> None:
            if self.on_listen is not None:
                self.on_listen()

        def open_settings() -> None:
            if self.on_open_settings is not None:
                self.on_open_settings()

        save_button = _TextButton(
            canvas, 20, 680, 138, 44, "Save", save, variant="filled", font=(body, 10, "bold")
        )
        talk_button = _TextButton(
            canvas, 170, 680, 138, 44, "Talk", talk, variant="tonal", font=(body, 10, "bold")
        )
        settings_button = _TextButton(
            canvas,
            320,
            680,
            140,
            44,
            "Settings",
            open_settings,
            variant="outlined",
            font=(body, 10, "bold"),
        )
        _TextButton(
            canvas, 20, 734, 72, 20, "Test alert", test_alert, variant="text", font=(body, 9)
        )
        _TextButton(
            canvas, 100, 734, 90, 20, "Clear saved", clear_saved, variant="text", font=(body, 9)
        )
        _TextButton(
            canvas, CARD_R - 44, 734, 44, 20, "Close", root.destroy, variant="text", font=(body, 9)
        )

        refresh_status()
        root.update_idletasks()
        right, bottom = _work_area(root)
        root.geometry(
            f"{WIDTH}x{HEIGHT}"
            f"+{max(0, right - WIDTH - 24)}"
            f"+{max(0, bottom - HEIGHT - 24)}"
        )
        root.after(80, lambda: _apply_window_chrome(root))
        root.after(400, lambda: _apply_window_chrome(root))
        root.after(100, self._poll, root)
        root.mainloop()

    def _poll(self, root: object) -> None:
        try:
            while True:
                command = self._queue.get_nowait()
                if command == "stop":
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(200, self._poll, root)
