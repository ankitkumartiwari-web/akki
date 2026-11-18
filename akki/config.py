from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppEntry:
    aliases: list[str] = field(default_factory=list)
    path: str | None = None
    command: str | None = None
    aumid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"aliases": self.aliases}
        if self.path:
            data["path"] = self.path
        if self.command:
            data["command"] = self.command
        if self.aumid:
            data["aumid"] = self.aumid
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppEntry":
        return cls(
            aliases=[str(a) for a in data.get("aliases", [])],
            path=data.get("path"),
            command=data.get("command"),
            aumid=data.get("aumid"),
        )


@dataclass(slots=True)
class LLMSettings:
    provider: str = "openrouter"
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 30.0
    cache_ttl_seconds: float = 3600.0
    enabled: bool = True
    local_enabled: bool = True
    local_first: bool = False
    local_model: str = "richardyoung/fable-qwen2.5-3b-abliterated"
    nsfw_local_model: str = "richardyoung/llama-3.2-3b-instruct-abliterated:Q4_K_M"
    nsfw_model: str = ""
    local_base_url: str = "http://127.0.0.1:11434/v1"
    local_timeout_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "provider": self.provider,
            "timeout_seconds": self.timeout_seconds,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "enabled": self.enabled,
            "local_enabled": self.local_enabled,
            "local_first": self.local_first,
            "local_model": self.local_model,
            "local_base_url": self.local_base_url,
            "local_timeout_seconds": self.local_timeout_seconds,
        }
        if self.nsfw_local_model:
            data["nsfw_local_model"] = self.nsfw_local_model
        if self.nsfw_model:
            data["nsfw_model"] = self.nsfw_model
        if self.model:
            data["model"] = self.model
        if self.base_url:
            data["base_url"] = self.base_url
        if self.api_key_env:
            data["api_key_env"] = self.api_key_env
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMSettings":
        base = cls()
        return cls(
            provider=data.get("provider", base.provider),
            model=data.get("model", base.model),
            base_url=data.get("base_url", base.base_url),
            api_key_env=data.get("api_key_env", base.api_key_env),
            timeout_seconds=float(data.get("timeout_seconds", base.timeout_seconds)),
            cache_ttl_seconds=float(
                data.get("cache_ttl_seconds", base.cache_ttl_seconds)
            ),
            enabled=bool(data.get("enabled", base.enabled)),
            local_enabled=bool(data.get("local_enabled", base.local_enabled)),
            local_first=bool(data.get("local_first", base.local_first)),
            local_model=str(data.get("local_model", base.local_model)),
            nsfw_local_model=str(
                data.get("nsfw_local_model", base.nsfw_local_model) or ""
            ),
            nsfw_model=str(data.get("nsfw_model", base.nsfw_model) or ""),
            local_base_url=str(data.get("local_base_url", base.local_base_url)),
            local_timeout_seconds=float(
                data.get("local_timeout_seconds", base.local_timeout_seconds)
            ),
        )


@dataclass(slots=True)
class VoiceSettings:
    auto_speak: bool = False
    rate: int = 1
    volume: int = 100
    tts_pitch: int = 0
    voice_name: str = ""
    stt_model: str = "small"
    stt_language: str = "auto"
    hotkey: str = "ctrl+space"
    hotkey_enabled: bool = False
    wake_word: str = "hey akki"
    wake_enabled: bool = True
    conversation_mode: bool = False
    tts_engine: str = "piper"
    edge_voice: str = "en-IN-PrabhatNeural"
    nsfw_edge_voice: str = "en-IN-NeerjaExpressiveNeural"
    hindi_edge_voice: str = "hi-IN-MadhurNeural"
    nsfw_hindi_edge_voice: str = "hi-IN-SwaraNeural"
    piper_voice: str = "en_US-lessac-medium"
    piper_speaker: int | None = None
    piper_length_scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_speak": self.auto_speak,
            "rate": self.rate,
            "volume": self.volume,
            "tts_pitch": self.tts_pitch,
            "voice_name": self.voice_name,
            "stt_model": self.stt_model,
            "stt_language": self.stt_language,
            "hotkey": self.hotkey,
            "hotkey_enabled": self.hotkey_enabled,
            "wake_word": self.wake_word,
            "wake_enabled": self.wake_enabled,
            "conversation_mode": self.conversation_mode,
            "tts_engine": self.tts_engine,
            "edge_voice": self.edge_voice,
            "nsfw_edge_voice": self.nsfw_edge_voice,
            "hindi_edge_voice": self.hindi_edge_voice,
            "nsfw_hindi_edge_voice": self.nsfw_hindi_edge_voice,
            "piper_voice": self.piper_voice,
            "piper_speaker": self.piper_speaker,
            "piper_length_scale": self.piper_length_scale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceSettings":
        base = cls()
        speaker = data.get("piper_speaker")
        return cls(
            auto_speak=bool(data.get("auto_speak", base.auto_speak)),
            rate=int(data.get("rate", base.rate)),
            volume=int(data.get("volume", base.volume)),
            tts_pitch=int(data.get("tts_pitch", base.tts_pitch)),
            voice_name=str(data.get("voice_name", base.voice_name)),
            stt_model=str(data.get("stt_model", base.stt_model)),
            stt_language=str(data.get("stt_language", base.stt_language)),
            hotkey=str(data.get("hotkey", base.hotkey)),
            hotkey_enabled=bool(data.get("hotkey_enabled", base.hotkey_enabled)),
            wake_word=str(data.get("wake_word", base.wake_word)),
            wake_enabled=bool(data.get("wake_enabled", base.wake_enabled)),
            conversation_mode=bool(
                data.get("conversation_mode", base.conversation_mode)
            ),
            tts_engine=str(data.get("tts_engine", base.tts_engine)),
            edge_voice=str(data.get("edge_voice", base.edge_voice)),
            nsfw_edge_voice=str(
                data.get("nsfw_edge_voice", base.nsfw_edge_voice)
            ),
            hindi_edge_voice=str(
                data.get("hindi_edge_voice", base.hindi_edge_voice)
            ),
            nsfw_hindi_edge_voice=str(
                data.get(
                    "nsfw_hindi_edge_voice", base.nsfw_hindi_edge_voice
                )
            ),
            piper_voice=str(data.get("piper_voice", base.piper_voice)),
            piper_speaker=None if speaker is None else int(speaker),
            piper_length_scale=float(
                data.get("piper_length_scale", base.piper_length_scale)
            ),
        )


@dataclass(slots=True)
class WebSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebSettings":
        base = cls()
        return cls(
            enabled=bool(data.get("enabled", base.enabled)),
            host=str(data.get("host", base.host)),
            port=int(data.get("port", base.port)),
        )


@dataclass(slots=True)
class AlertSettings:
    enabled: bool = False
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token_env: str = "AKKI_NTFY_TOKEN"
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password_env: str = "AKKI_IMAP_PASSWORD"
    imap_folder: str = "INBOX"
    poll_seconds: float = 300.0
    importance_threshold: float = 0.65
    max_messages: int = 10
    timeout_seconds: float = 20.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ntfy_server": self.ntfy_server,
            "ntfy_topic": self.ntfy_topic,
            "ntfy_token_env": self.ntfy_token_env,
            "imap_host": self.imap_host,
            "imap_port": self.imap_port,
            "imap_user": self.imap_user,
            "imap_password_env": self.imap_password_env,
            "imap_folder": self.imap_folder,
            "poll_seconds": self.poll_seconds,
            "importance_threshold": self.importance_threshold,
            "max_messages": self.max_messages,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlertSettings":
        base = cls()
        return cls(
            enabled=bool(data.get("enabled", base.enabled)),
            ntfy_server=str(data.get("ntfy_server", base.ntfy_server)),
            ntfy_topic=str(data.get("ntfy_topic", base.ntfy_topic)),
            ntfy_token_env=str(data.get("ntfy_token_env", base.ntfy_token_env)),
            imap_host=str(data.get("imap_host", base.imap_host)),
            imap_port=int(data.get("imap_port", base.imap_port)),
            imap_user=str(data.get("imap_user", base.imap_user)),
            imap_password_env=str(
                data.get("imap_password_env", base.imap_password_env)
            ),
            imap_folder=str(data.get("imap_folder", base.imap_folder)),
            poll_seconds=float(data.get("poll_seconds", base.poll_seconds)),
            importance_threshold=float(
                data.get("importance_threshold", base.importance_threshold)
            ),
            max_messages=int(data.get("max_messages", base.max_messages)),
            timeout_seconds=float(data.get("timeout_seconds", base.timeout_seconds)),
        )


@dataclass(slots=True)
class DesktopSettings:
    tray_enabled: bool = False
    widget_enabled: bool = False
    bubble_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tray_enabled": self.tray_enabled,
            "widget_enabled": self.widget_enabled,
            "bubble_enabled": self.bubble_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesktopSettings":
        base = cls()
        return cls(
            tray_enabled=bool(data.get("tray_enabled", base.tray_enabled)),
            widget_enabled=bool(
                data.get("widget_enabled", base.widget_enabled)
            ),
            bubble_enabled=bool(data.get("bubble_enabled", base.bubble_enabled)),
        )


@dataclass(slots=True)
class MCPServerSettings:
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 15.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "env": self.env,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPServerSettings":
        base = cls()
        command = data.get("command", base.command)
        if isinstance(command, str):
            command = [command]
        env = data.get("env", base.env)
        return cls(
            command=[str(item) for item in command],
            env={str(key): str(value) for key, value in env.items()},
            enabled=bool(data.get("enabled", base.enabled)),
            timeout_seconds=float(data.get("timeout_seconds", base.timeout_seconds)),
        )


@dataclass(slots=True)
class Config:
    profile: str = "sovereign"
    apps: dict[str, AppEntry] = field(default_factory=dict)
    search_roots: list[Path] = field(default_factory=list)
    screenshot_dir: Path = field(default_factory=lambda: Path.home() / "Pictures" / "AKKI")
    db_path: Path = field(default_factory=lambda: database_path())
    search_engine: str = "duckduckgo"
    max_depth: int = 6
    max_results: int = 20
    timeout_seconds: float = 5.0
    llm: LLMSettings = field(default_factory=LLMSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    web: WebSettings = field(default_factory=WebSettings)
    alerts: AlertSettings = field(default_factory=AlertSettings)
    desktop: DesktopSettings = field(default_factory=DesktopSettings)
    mcp_servers: dict[str, MCPServerSettings] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "Config":
        home = Path.home()
        candidates = [
            home / "Desktop",
            home / "OneDrive" / "Desktop",
            home / "Documents",
            home / "OneDrive" / "Documents",
            home / "Downloads",
            home / "OneDrive" / "Downloads",
            home / "Projects",
            home / "OneDrive" / "Projects",
            home / "Code",
            home / "Dev",
        ]
        roots = list(dict.fromkeys(p for p in candidates if p.exists()))
        return cls(
            apps={
                "vscode": AppEntry(["code", "vs code", "vscode"], command="code"),
                "notepad": AppEntry(["notepad"], command="notepad"),
                "calculator": AppEntry(
                    ["calculator", "calc"],
                    aumid="Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                ),
                "explorer": AppEntry(["explorer", "file explorer", "files"], command="explorer"),
                "chrome": AppEntry(["chrome", "google chrome"], command="chrome"),
                "edge": AppEntry(["edge", "microsoft edge"], command="msedge"),
                "terminal": AppEntry(["terminal", "windows terminal", "wt"], command="wt"),
                "paint": AppEntry(["paint", "mspaint"], command="mspaint"),
                "settings": AppEntry(
                    ["settings", "windows settings"],
                    aumid="windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel",
                ),
            },
            search_roots=[p for p in roots if p.exists()] or [home],
        )

    def find_app(self, alias: str) -> tuple[str, AppEntry] | None:
        wanted = alias.strip().lower()
        for name, entry in self.apps.items():
            if wanted == name.lower() or wanted in (a.lower() for a in entry.aliases):
                return name, entry
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "apps": {name: entry.to_dict() for name, entry in self.apps.items()},
            "search_roots": [str(p) for p in self.search_roots],
            "screenshot_dir": str(self.screenshot_dir),
            "db_path": str(self.db_path),
            "search_engine": self.search_engine,
            "max_depth": self.max_depth,
            "max_results": self.max_results,
            "timeout_seconds": self.timeout_seconds,
            "llm": self.llm.to_dict(),
            "voice": self.voice.to_dict(),
            "web": self.web.to_dict(),
            "alerts": self.alerts.to_dict(),
            "desktop": self.desktop.to_dict(),
            "mcp_servers": {
                name: server.to_dict() for name, server in self.mcp_servers.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        base = cls.default()
        apps = {
            name: AppEntry.from_dict(value)
            for name, value in data.get("apps", {}).items()
        }
        return cls(
            profile=data.get("profile", base.profile),
            apps=apps or base.apps,
            search_roots=[Path(p).expanduser() for p in data.get("search_roots", [])]
            or base.search_roots,
            screenshot_dir=Path(data.get("screenshot_dir", base.screenshot_dir)).expanduser(),
            db_path=Path(data.get("db_path", base.db_path)).expanduser(),
            search_engine=data.get("search_engine", base.search_engine),
            max_depth=int(data.get("max_depth", base.max_depth)),
            max_results=int(data.get("max_results", base.max_results)),
            timeout_seconds=float(data.get("timeout_seconds", base.timeout_seconds)),
            llm=LLMSettings.from_dict(data.get("llm", {})),
            voice=VoiceSettings.from_dict(data.get("voice", {})),
            web=WebSettings.from_dict(data.get("web", {})),
            alerts=AlertSettings.from_dict(data.get("alerts", {})),
            desktop=DesktopSettings.from_dict(data.get("desktop", {})),
            mcp_servers={
                name: MCPServerSettings.from_dict(value)
                for name, value in data.get("mcp_servers", {}).items()
            },
        )


def config_path() -> Path:
    override = os.environ.get("AKKI_CONFIG")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "AKKI" / "config.json"


def database_path() -> Path:
    override = os.environ.get("AKKI_DB")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "AKKI" / "akki.db"


def save_config(config: Config, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    return target


def load_config(path: Path | None = None, *, create: bool = True) -> Config:
    target = path or config_path()
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
        return Config.from_dict(data)
    config = Config.default()
    if create:
        save_config(config, target)
    return config


def apply_config(target: Config, source: Config) -> None:
    for name in Config.__dataclass_fields__:
        setattr(target, name, getattr(source, name))
