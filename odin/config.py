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
    local_first: bool = True
    local_model: str = "richardyoung/fable-qwen2.5-3b-abliterated"
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
    voice_name: str = ""
    stt_model: str = "small"
    stt_language: str = "auto"
    hotkey: str = "ctrl+space"
    hotkey_enabled: bool = False
    tts_engine: str = "piper"
    piper_voice: str = "en_US-lessac-medium"
    piper_speaker: int | None = None
    piper_length_scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_speak": self.auto_speak,
            "rate": self.rate,
            "volume": self.volume,
            "voice_name": self.voice_name,
            "stt_model": self.stt_model,
            "stt_language": self.stt_language,
            "hotkey": self.hotkey,
            "hotkey_enabled": self.hotkey_enabled,
            "tts_engine": self.tts_engine,
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
            voice_name=str(data.get("voice_name", base.voice_name)),
            stt_model=str(data.get("stt_model", base.stt_model)),
            stt_language=str(data.get("stt_language", base.stt_language)),
            hotkey=str(data.get("hotkey", base.hotkey)),
            hotkey_enabled=bool(data.get("hotkey_enabled", base.hotkey_enabled)),
            tts_engine=str(data.get("tts_engine", base.tts_engine)),
            piper_voice=str(data.get("piper_voice", base.piper_voice)),
            piper_speaker=None if speaker is None else int(speaker),
            piper_length_scale=float(
                data.get("piper_length_scale", base.piper_length_scale)
            ),
        )


@dataclass(slots=True)
class Config:
    profile: str = "sovereign"
    apps: dict[str, AppEntry] = field(default_factory=dict)
    search_roots: list[Path] = field(default_factory=list)
    screenshot_dir: Path = field(default_factory=lambda: Path.home() / "Pictures" / "ODIN")
    db_path: Path = field(default_factory=lambda: database_path())
    search_engine: str = "duckduckgo"
    max_depth: int = 6
    max_results: int = 20
    timeout_seconds: float = 5.0
    llm: LLMSettings = field(default_factory=LLMSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)

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
        )


def config_path() -> Path:
    override = os.environ.get("ODIN_CONFIG")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "ODIN" / "config.json"


def database_path() -> Path:
    override = os.environ.get("ODIN_DB")
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "ODIN" / "odin.db"


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
