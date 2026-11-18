from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from .config import Config, config_path, load_config, save_config

PROFILE_VALUES = ("sovereign", "nsfw", "guarded")


class SettingsPanel:
    def __init__(
        self,
        config: Config,
        *,
        config_file: Path | None = None,
        on_save: Callable[[Config], None] | None = None,
    ) -> None:
        self.config = config
        self.config_file = config_file or config_path()
        self.on_save = on_save
        self._thread: threading.Thread | None = None
        self._vars: dict[str, object] = {}

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.active:
            return
        self._thread = threading.Thread(
            target=self._run, name="akki-settings-panel", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        root = tk.Tk()
        root.title("AKKI Settings")
        root.minsize(680, 560)
        root.configure(bg="#0b1220")

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#0b1220")
        style.configure("TLabel", background="#0b1220", foreground="#dbeafe")
        style.configure(
            "TCheckbutton", background="#0b1220", foreground="#dbeafe"
        )
        style.configure("TNotebook", background="#0b1220", borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#111c33",
            foreground="#dbeafe",
            padding=(12, 6),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("TButton", padding=(10, 5))
        style.configure("Accent.TButton", foreground="#ffffff", background="#1d4ed8")

        self._vars = {
            "profile": tk.StringVar(value=self.config.profile),
            "auto_speak": tk.BooleanVar(value=self.config.voice.auto_speak),
            "hotkey_enabled": tk.BooleanVar(
                value=self.config.voice.hotkey_enabled
            ),
            "wake_enabled": tk.BooleanVar(value=self.config.voice.wake_enabled),
            "stt_model": tk.StringVar(value=self.config.voice.stt_model),
            "stt_language": tk.StringVar(value=self.config.voice.stt_language),
            "hotkey": tk.StringVar(value=self.config.voice.hotkey),
            "wake_word": tk.StringVar(value=self.config.voice.wake_word),
            "tts_engine": tk.StringVar(value=self.config.voice.tts_engine),
            "piper_voice": tk.StringVar(value=self.config.voice.piper_voice),
            "piper_speaker": tk.StringVar(
                value=""
                if self.config.voice.piper_speaker is None
                else str(self.config.voice.piper_speaker)
            ),
            "piper_length_scale": tk.StringVar(
                value=str(self.config.voice.piper_length_scale)
            ),
            "web_enabled": tk.BooleanVar(value=self.config.web.enabled),
            "web_host": tk.StringVar(value=self.config.web.host),
            "web_port": tk.StringVar(value=str(self.config.web.port)),
            "tray_enabled": tk.BooleanVar(value=self.config.desktop.tray_enabled),
            "widget_enabled": tk.BooleanVar(
                value=self.config.desktop.widget_enabled
            ),
            "bubble_enabled": tk.BooleanVar(
                value=self.config.desktop.bubble_enabled
            ),
            "alerts_enabled": tk.BooleanVar(value=self.config.alerts.enabled),
            "ntfy_server": tk.StringVar(value=self.config.alerts.ntfy_server),
            "ntfy_topic": tk.StringVar(value=self.config.alerts.ntfy_topic),
            "ntfy_token_env": tk.StringVar(
                value=self.config.alerts.ntfy_token_env
            ),
            "imap_host": tk.StringVar(value=self.config.alerts.imap_host),
            "imap_port": tk.StringVar(value=str(self.config.alerts.imap_port)),
            "imap_user": tk.StringVar(value=self.config.alerts.imap_user),
            "imap_password_env": tk.StringVar(
                value=self.config.alerts.imap_password_env
            ),
            "imap_folder": tk.StringVar(value=self.config.alerts.imap_folder),
            "poll_seconds": tk.StringVar(
                value=str(self.config.alerts.poll_seconds)
            ),
            "importance_threshold": tk.StringVar(
                value=str(self.config.alerts.importance_threshold)
            ),
            "max_messages": tk.StringVar(
                value=str(self.config.alerts.max_messages)
            ),
            "timeout_seconds": tk.StringVar(
                value=str(self.config.alerts.timeout_seconds)
            ),
        }

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        def entry(tab: object, row: int, label: str, key: str) -> None:
            ttk.Label(tab, text=label).grid(
                row=row, column=0, sticky="w", padx=8, pady=5
            )
            ttk.Entry(tab, textvariable=self._vars[key], width=44).grid(
                row=row, column=1, sticky="ew", padx=8, pady=5
            )

        def check(tab: object, row: int, label: str, key: str) -> None:
            ttk.Checkbutton(tab, text=label, variable=self._vars[key]).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=8, pady=5
            )

        def combo(
            tab: object, row: int, label: str, key: str, values: tuple[str, ...]
        ) -> None:
            ttk.Label(tab, text=label).grid(
                row=row, column=0, sticky="w", padx=8, pady=5
            )
            ttk.Combobox(
                tab,
                textvariable=self._vars[key],
                values=values,
                state="readonly",
                width=40,
            ).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        general = ttk.Frame(notebook)
        general.columnconfigure(1, weight=1)
        notebook.add(general, text="General")
        combo(general, 0, "Mode", "profile", PROFILE_VALUES)
        ttk.Label(
            general,
            text=(
                "sovereign and nsfw allow adult language and fictional adult "
                "content between consenting adults; guarded is safe for work. "
                "Hard limits still apply."
            ),
            wraplength=560,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=5)
        ttk.Label(general, text=f"Config: {self.config_file}").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=5
        )
        ttk.Label(general, text=f"Database: {self.config.db_path}").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=8, pady=5
        )

        voice = ttk.Frame(notebook)
        voice.columnconfigure(1, weight=1)
        notebook.add(voice, text="Voice")
        check(voice, 0, "Speak replies automatically", "auto_speak")
        check(voice, 1, "Enable Ctrl+Space push to talk", "hotkey_enabled")
        check(voice, 2, "Enable wake word", "wake_enabled")
        combo(
            voice,
            3,
            "Recognition model",
            "stt_model",
            ("tiny", "base", "small", "medium", "large-v3"),
        )
        entry(voice, 4, "Recognition language", "stt_language")
        entry(voice, 5, "Hotkey", "hotkey")
        entry(voice, 6, "Wake phrase", "wake_word")
        combo(voice, 7, "TTS engine", "tts_engine", ("piper", "sapi"))
        entry(voice, 8, "Piper voice", "piper_voice")
        entry(voice, 9, "Piper speaker", "piper_speaker")
        entry(voice, 10, "Piper length scale", "piper_length_scale")

        web = ttk.Frame(notebook)
        web.columnconfigure(1, weight=1)
        notebook.add(web, text="Web UI")
        check(web, 0, "Enable the local web UI", "web_enabled")
        entry(web, 1, "Host", "web_host")
        entry(web, 2, "Port", "web_port")

        desktop = ttk.Frame(notebook)
        desktop.columnconfigure(1, weight=1)
        notebook.add(desktop, text="Desktop")
        check(desktop, 0, "Start the tray icon", "tray_enabled")
        check(desktop, 1, "Start the desktop access widget", "widget_enabled")
        check(desktop, 2, "Show the listening bubble", "bubble_enabled")
        ttk.Label(
            desktop,
            text=(
                "The tray icon opens this window. The desktop widget has quick "
                "mode, password, and talk controls. The listening bubble appears "
                "near the bottom-right while the microphone is active. Tray, "
                "widget, web, hotkey, and wake changes may need a restart to "
                "start or stop their listeners."
            ),
            wraplength=560,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        alert_tab = ttk.Frame(notebook)
        alert_tab.columnconfigure(1, weight=1)
        notebook.add(alert_tab, text="Mobile alerts")
        check(alert_tab, 0, "Forward important mail to my phone", "alerts_enabled")
        entry(alert_tab, 1, "ntfy server", "ntfy_server")
        entry(alert_tab, 2, "ntfy topic", "ntfy_topic")
        entry(alert_tab, 3, "ntfy token env", "ntfy_token_env")
        entry(alert_tab, 4, "IMAP host", "imap_host")
        entry(alert_tab, 5, "IMAP port", "imap_port")
        entry(alert_tab, 6, "IMAP user", "imap_user")
        entry(alert_tab, 7, "IMAP password env", "imap_password_env")
        entry(alert_tab, 8, "IMAP folder", "imap_folder")
        entry(alert_tab, 9, "Poll seconds", "poll_seconds")
        entry(alert_tab, 10, "Importance threshold 0-1", "importance_threshold")
        entry(alert_tab, 11, "Max messages per check", "max_messages")
        entry(alert_tab, 12, "Network timeout seconds", "timeout_seconds")

        mcp = ttk.Frame(notebook)
        notebook.add(mcp, text="MCP")
        names = ", ".join(self.config.mcp_servers) or "(none configured)"
        ttk.Label(mcp, text=f"Configured servers: {names}", wraplength=560).grid(
            row=0, column=0, sticky="w", padx=8, pady=8
        )
        ttk.Button(
            mcp,
            text="Open config file",
            command=lambda: os.startfile(str(self.config_file)),
        ).grid(row=1, column=0, sticky="w", padx=8, pady=8)

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(
            buttons, text="Save", style="Accent.TButton", command=lambda: save()
        ).pack(side="right", padx=4)
        ttk.Button(buttons, text="Reload", command=lambda: reload()).pack(
            side="right", padx=4
        )
        ttk.Button(buttons, text="Close", command=root.destroy).pack(
            side="right", padx=4
        )

        def collect() -> Config:
            new = Config.from_dict(self.config.to_dict())
            new.profile = str(self._vars["profile"].get()).strip() or "sovereign"
            new.voice.auto_speak = bool(self._vars["auto_speak"].get())
            new.voice.hotkey_enabled = bool(self._vars["hotkey_enabled"].get())
            new.voice.wake_enabled = bool(self._vars["wake_enabled"].get())
            new.voice.stt_model = str(self._vars["stt_model"].get()).strip()
            new.voice.stt_language = str(
                self._vars["stt_language"].get()
            ).strip()
            new.voice.hotkey = str(self._vars["hotkey"].get()).strip()
            new.voice.wake_word = str(self._vars["wake_word"].get()).strip()
            new.voice.tts_engine = str(self._vars["tts_engine"].get()).strip()
            new.voice.piper_voice = str(
                self._vars["piper_voice"].get()
            ).strip()
            speaker = str(self._vars["piper_speaker"].get()).strip()
            new.voice.piper_speaker = int(speaker) if speaker else None
            new.voice.piper_length_scale = float(
                str(self._vars["piper_length_scale"].get()).strip()
            )
            new.web.enabled = bool(self._vars["web_enabled"].get())
            new.web.host = str(self._vars["web_host"].get()).strip()
            new.web.port = int(str(self._vars["web_port"].get()).strip())
            new.desktop.tray_enabled = bool(
                self._vars["tray_enabled"].get()
            )
            new.desktop.widget_enabled = bool(
                self._vars["widget_enabled"].get()
            )
            new.desktop.bubble_enabled = bool(
                self._vars["bubble_enabled"].get()
            )
            new.alerts.enabled = bool(self._vars["alerts_enabled"].get())
            new.alerts.ntfy_server = str(
                self._vars["ntfy_server"].get()
            ).strip()
            new.alerts.ntfy_topic = str(
                self._vars["ntfy_topic"].get()
            ).strip()
            new.alerts.ntfy_token_env = str(
                self._vars["ntfy_token_env"].get()
            ).strip()
            new.alerts.imap_host = str(self._vars["imap_host"].get()).strip()
            new.alerts.imap_port = int(
                str(self._vars["imap_port"].get()).strip()
            )
            new.alerts.imap_user = str(self._vars["imap_user"].get()).strip()
            new.alerts.imap_password_env = str(
                self._vars["imap_password_env"].get()
            ).strip()
            new.alerts.imap_folder = str(
                self._vars["imap_folder"].get()
            ).strip()
            new.alerts.poll_seconds = float(
                str(self._vars["poll_seconds"].get()).strip()
            )
            new.alerts.importance_threshold = float(
                str(self._vars["importance_threshold"].get()).strip()
            )
            new.alerts.max_messages = int(
                str(self._vars["max_messages"].get()).strip()
            )
            new.alerts.timeout_seconds = float(
                str(self._vars["timeout_seconds"].get()).strip()
            )
            if new.web.port < 1 or new.web.port > 65535:
                raise ValueError("web port must be 1..65535")
            if new.alerts.imap_port < 1 or new.alerts.imap_port > 65535:
                raise ValueError("IMAP port must be 1..65535")
            if new.alerts.poll_seconds < 10:
                raise ValueError("poll seconds must be at least 10")
            if not 0 <= new.alerts.importance_threshold <= 1:
                raise ValueError("importance threshold must be 0..1")
            if new.alerts.max_messages < 1:
                raise ValueError("max messages must be at least 1")
            if new.voice.piper_length_scale <= 0:
                raise ValueError("piper length scale must be positive")
            return new

        def save() -> None:
            try:
                new = collect()
            except ValueError as exc:
                messagebox.showerror("AKKI Settings", str(exc), parent=root)
                return
            try:
                save_config(new, self.config_file)
            except OSError as exc:
                messagebox.showerror("AKKI Settings", str(exc), parent=root)
                return
            self.config = new
            if self.on_save is not None:
                self.on_save(new)
            messagebox.showinfo(
                "AKKI Settings", "Settings saved.", parent=root
            )

        def reload() -> None:
            try:
                new = load_config(self.config_file)
            except (OSError, ValueError) as exc:
                messagebox.showerror("AKKI Settings", str(exc), parent=root)
                return
            self.config = new
            self._load_vars(new)
            messagebox.showinfo(
                "AKKI Settings", "Settings reloaded.", parent=root
            )

        root.after(50, self._center, root)
        root.mainloop()

    def _load_vars(self, config: Config) -> None:
        values: dict[str, object] = {
            "profile": config.profile,
            "auto_speak": config.voice.auto_speak,
            "hotkey_enabled": config.voice.hotkey_enabled,
            "wake_enabled": config.voice.wake_enabled,
            "stt_model": config.voice.stt_model,
            "stt_language": config.voice.stt_language,
            "hotkey": config.voice.hotkey,
            "wake_word": config.voice.wake_word,
            "tts_engine": config.voice.tts_engine,
            "piper_voice": config.voice.piper_voice,
            "piper_speaker": ""
            if config.voice.piper_speaker is None
            else str(config.voice.piper_speaker),
            "piper_length_scale": str(config.voice.piper_length_scale),
            "web_enabled": config.web.enabled,
            "web_host": config.web.host,
            "web_port": str(config.web.port),
            "tray_enabled": config.desktop.tray_enabled,
            "widget_enabled": config.desktop.widget_enabled,
            "bubble_enabled": config.desktop.bubble_enabled,
            "alerts_enabled": config.alerts.enabled,
            "ntfy_server": config.alerts.ntfy_server,
            "ntfy_topic": config.alerts.ntfy_topic,
            "ntfy_token_env": config.alerts.ntfy_token_env,
            "imap_host": config.alerts.imap_host,
            "imap_port": str(config.alerts.imap_port),
            "imap_user": config.alerts.imap_user,
            "imap_password_env": config.alerts.imap_password_env,
            "imap_folder": config.alerts.imap_folder,
            "poll_seconds": str(config.alerts.poll_seconds),
            "importance_threshold": str(config.alerts.importance_threshold),
            "max_messages": str(config.alerts.max_messages),
            "timeout_seconds": str(config.alerts.timeout_seconds),
        }
        for key, value in values.items():
            self._vars[key].set(value)

    @staticmethod
    def _center(root: object) -> None:
        try:
            root.update_idletasks()
            width = max(680, root.winfo_width())
            height = max(560, root.winfo_height())
            x = (root.winfo_screenwidth() - width) // 2
            y = (root.winfo_screenheight() - height) // 2
            root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass
