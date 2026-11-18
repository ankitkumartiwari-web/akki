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
        from tkinter import messagebox, ttk

        root = tk.Tk()
        root.title("AKKI Desktop")
        root.minsize(390, 600)
        root.configure(bg="#0b1220")
        root.attributes("-topmost", True)

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
        style.configure("TButton", padding=(8, 4))
        style.configure(
            "Accent.TButton", foreground="#ffffff", background="#1d4ed8"
        )

        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        title = ttk.Label(
            main,
            text="AKKI",
            font=("Segoe UI", 16, "bold"),
            foreground="#6ee7ff",
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            main,
            text="Desktop access, passwords, and mode",
            foreground="#93c5fd",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(main, text="Mode").grid(row=2, column=0, sticky="w", pady=4)
        mode_var = tk.StringVar(value=self.config.profile)
        ttk.Combobox(
            main,
            textvariable=mode_var,
            values=PROFILE_VALUES,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew", pady=4)

        alert_status = tk.StringVar()
        ttk.Label(main, text="Mobile alerts").grid(
            row=3, column=0, sticky="w", pady=4
        )
        ttk.Label(main, textvariable=alert_status).grid(
            row=3, column=1, sticky="w", pady=4
        )

        ttk.Separator(main).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(
            main,
            text="Passwords and tokens",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=5, column=0, columnspan=2, sticky="w")

        imap_env = self.config.alerts.imap_password_env or "AKKI_IMAP_PASSWORD"
        ntfy_env = self.config.alerts.ntfy_token_env or "AKKI_NTFY_TOKEN"
        cloud_env = (
            resolve_endpoint(self.config.llm)[2]
            or self.config.llm.api_key_env
            or "OPENROUTER_API_KEY"
        )

        password_vars: dict[str, tk.StringVar] = {}
        password_entries: list[object] = []
        secret_status: dict[str, tk.StringVar] = {}

        def add_secret(
            row: int, label: str, env_name: str, hint: str
        ) -> None:
            ttk.Label(main, text=label).grid(
                row=row, column=0, sticky="w", pady=(8, 0)
            )
            variable = tk.StringVar()
            password_vars[env_name] = variable
            entry = ttk.Entry(main, textvariable=variable, show="*")
            entry.grid(row=row, column=1, sticky="ew", pady=(8, 0))
            password_entries.append(entry)
            status = tk.StringVar()
            secret_status[env_name] = status
            ttk.Label(main, textvariable=status, foreground="#93c5fd").grid(
                row=row + 1, column=1, sticky="w"
            )
            ttk.Label(main, text=hint, foreground="#64748b").grid(
                row=row + 1, column=0, sticky="w"
            )

        add_secret(6, "IMAP password", imap_env, imap_env)
        add_secret(8, "ntfy token", ntfy_env, ntfy_env)
        add_secret(10, "Cloud API key", cloud_env, cloud_env)

        show_passwords = tk.BooleanVar(value=False)

        def toggle_passwords() -> None:
            mask = "" if show_passwords.get() else "*"
            for entry in password_entries:
                entry.configure(show=mask)

        ttk.Checkbutton(
            main,
            text="Show passwords",
            variable=show_passwords,
            command=toggle_passwords,
        ).grid(row=12, column=0, sticky="w", pady=(8, 0))

        start_with_akki = tk.BooleanVar(
            value=self.config.desktop.widget_enabled
        )
        ttk.Checkbutton(
            main,
            text="Start this widget with AKKI",
            variable=start_with_akki,
        ).grid(row=12, column=1, sticky="w", pady=(8, 0))

        pin_var = tk.BooleanVar(value=True)

        def toggle_pin() -> None:
            root.attributes("-topmost", bool(pin_var.get()))

        ttk.Checkbutton(
            main, text="Always on top", variable=pin_var, command=toggle_pin
        ).grid(row=13, column=0, sticky="w", pady=(4, 0))

        def refresh_status() -> None:
            alerts_on = "on" if self.config.alerts.enabled else "off"
            host = self.config.alerts.imap_host or "not configured"
            alert_status.set(f"{alerts_on} ({host})")
            for env_name, variable in secret_status.items():
                variable.set(
                    "saved" if self.secrets.has_secret(env_name) else "not saved"
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
                messagebox.showerror("AKKI Desktop", str(exc), parent=root)
                return
            messagebox.showinfo(
                "AKKI Desktop", "Mode and passwords saved.", parent=root
            )

        def clear_saved() -> None:
            if not messagebox.askyesno(
                "AKKI Desktop",
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
                messagebox.showerror("AKKI Desktop", str(exc), parent=root)
                return
            refresh_status()

        def test_alert() -> None:
            if self.on_test_alert is None:
                return
            try:
                save_entered_secrets()
            except (OSError, SecretError) as exc:
                messagebox.showerror("AKKI Desktop", str(exc), parent=root)
                return
            refresh_status()
            result = self.on_test_alert()
            if result.ok:
                messagebox.showinfo("AKKI Desktop", result.message, parent=root)
            else:
                messagebox.showerror("AKKI Desktop", result.message, parent=root)

        def talk() -> None:
            if self.on_listen is not None:
                self.on_listen()

        def open_settings() -> None:
            if self.on_open_settings is not None:
                self.on_open_settings()

        buttons = ttk.Frame(main)
        buttons.grid(
            row=14, column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )
        ttk.Button(
            buttons, text="Save", style="Accent.TButton", command=save
        ).pack(side="left", padx=(0, 4))
        ttk.Button(buttons, text="Talk", command=talk).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Test alert", command=test_alert).pack(
            side="left", padx=4
        )
        ttk.Button(
            buttons, text="Full settings", command=open_settings
        ).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=root.destroy).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(buttons, text="Clear saved", command=clear_saved).pack(
            side="right", padx=4
        )

        refresh_status()
        root.update_idletasks()
        width = max(390, root.winfo_reqwidth())
        height = max(600, root.winfo_reqheight())
        root.geometry(
            f"{width}x{height}"
            f"+{root.winfo_screenwidth() - width - 30}"
            f"+{root.winfo_screenheight() - height - 80}"
        )
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
