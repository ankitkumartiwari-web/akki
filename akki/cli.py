from __future__ import annotations

import argparse
import logging
import os
import queue
import re
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from . import __version__
from . import alerts
from .config import Config, apply_config, config_path, load_config, save_config
from .conversation import Conversation, resolve_followup
from .hotkey import HotkeyError, HotkeyListener, hotkey_supported
from .indicator import ListeningIndicator
from .wake import WakeWordError, WakeWordListener, wake_supported
from . import knowledge
from . import planner
from .facts import lookup_officeholder
from . import scheduler
from . import speaker
from . import vision
from .reminders import format_duration, parse_reminder
from .llm import ask_cloud, ask_local, build_system_prompt, resolve_endpoint
from .logsetup import configure_logging, log_path
from .mcp import MCPManager
from .language import is_devanagari as _is_devanagari
from .language import is_latin_hindi
from .models import ActionLevel, ActionRequest, ToolResult
from .panel import SettingsPanel
from .permissions import ask_confirmation
from .registry import ToolRegistry
from .router import route
from .secrets import SecretError, SecretsStore
from .shortcut import install_desktop_widget_shortcut
from .storage import Storage, make_cache_key
from .tray import TrayError, TrayIcon, tray_supported
from .webui import WebUI, WebUIError
from .widget import DesktopWidget
from .voice import (
    VoiceError,
    capture_push,
    ensure_piper,
    list_voices,
    listen,
    listen_push,
    piper_catalog,
    piper_num_speakers,
    piper_ready,
    piper_voice_urls,
    prewarm_piper,
    resolve_voice_id,
    speak,
)

logger = logging.getLogger("akki.cli")
from .tools.files import resolve_targets
from .tools import (
    announce_reminder,
    capture_camera,
    change_volume,
    clipboard_read,
    clipboard_write,
    compose_message,
    detect_faces,
    find_files,
    inspect_path,
    launch_app,
    list_apps,
    list_folder,
    lock_screen,
    open_in_app,
    open_path,
    open_url,
    read_file,
    read_url,
    remember_fact,
    take_screenshot,
    web_search,
)

BANNER = "AKKI {version} - local-first assistant. Type :help for commands."


def build_registry(config: Config, storage: Storage | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "launch_app",
        "Launch an application by name or alias (uses Start Menu discovery)",
        ActionLevel.REVERSIBLE,
        partial(launch_app, config=config),
        {"alias": "application name or alias"},
    )
    registry.register(
        "mobile_alert",
        "Send a short alert to the user's phone",
        ActionLevel.REVERSIBLE,
        partial(alerts.send_mobile_alert, config=config),
        {"title": "short alert title", "message": "alert body"},
    )
    registry.register(
        "open_in_app",
        "Open a file or folder in an application by name or alias (uses Start Menu discovery)",
        ActionLevel.REVERSIBLE,
        partial(open_in_app, config=config),
        {"alias": "application", "target": "file or folder"},
    )
    registry.register(
        "open_url",
        "Open a website in the default browser",
        ActionLevel.REVERSIBLE,
        partial(open_url, config=config),
        {"url": "http or https URL"},
    )
    registry.register(
        "web_search",
        "Search the web in the default browser",
        ActionLevel.REVERSIBLE,
        partial(web_search, config=config),
        {"query": "search terms"},
    )
    registry.register(
        "read_url",
        "Read text content from a web page",
        ActionLevel.READ_ONLY,
        partial(read_url, config=config),
        {"url": "http or https URL"},
    )
    registry.register(
        "camera_capture",
        "Capture a camera frame",
        ActionLevel.READ_ONLY,
        capture_camera,
        {},
    )
    registry.register(
        "face_detect",
        "Detect faces in an image",
        ActionLevel.READ_ONLY,
        detect_faces,
        {"image_b64": "base64 encoded image"},
    )
    registry.register(
        "lock_screen",
        "Lock the Windows screen",
        ActionLevel.REVERSIBLE,
        lock_screen,
        {},
    )
    registry.register(
        "clipboard_read",
        "Read the Windows clipboard text",
        ActionLevel.READ_ONLY,
        clipboard_read,
        {},
    )
    registry.register(
        "clipboard_write",
        "Write text to the Windows clipboard",
        ActionLevel.SENSITIVE,
        clipboard_write,
        {"text": "text to copy"},
    )
    registry.register(
        "compose_message",
        "Copy a dictated message to the clipboard and save a draft",
        ActionLevel.REVERSIBLE,
        compose_message,
        {"text": "message text"},
    )
    registry.register(
        "open_path",
        "Open a file or folder with its default handler",
        ActionLevel.REVERSIBLE,
        partial(open_path, config=config),
        {"path": "file or folder path"},
    )
    registry.register(
        "find_files",
        "Find files and folders under the configured search roots",
        ActionLevel.READ_ONLY,
        partial(find_files, config=config),
        {"query": "name fragment"},
    )
    registry.register(
        "list_folder",
        "List files and folders with sizes and modified dates",
        ActionLevel.READ_ONLY,
        partial(list_folder, config=config),
        {
            "target": "file, folder, or alias such as desktop",
            "recursive": {
                "type": "boolean",
                "description": "include nested files",
                "optional": True,
            },
        },
    )
    registry.register(
        "read_file",
        "Read the text contents and metadata of a local file",
        ActionLevel.READ_ONLY,
        partial(read_file, config=config),
        {"target": "file name or path"},
    )
    registry.register(
        "inspect_path",
        "Read a file or list a folder, whichever the target is",
        ActionLevel.READ_ONLY,
        partial(inspect_path, config=config),
        {
            "target": "file or folder",
            "recursive": {
                "type": "boolean",
                "description": "include nested files",
                "optional": True,
            },
        },
    )
    registry.register(
        "remember_fact",
        "Store an important fact in long-term memory",
        ActionLevel.REVERSIBLE,
        partial(remember_fact, storage=storage),
        {"fact": "fact or detail to remember"},
    )
    registry.register(
        "reminder",
        "Speak a due reminder aloud",
        ActionLevel.READ_ONLY,
        partial(announce_reminder, config=config),
        {"text": "reminder text"},
    )
    registry.register(
        "screenshot",
        "Capture the screen to the screenshot folder",
        ActionLevel.READ_ONLY,
        partial(take_screenshot, config=config),
    )
    registry.register(
        "volume",
        "Change system volume",
        ActionLevel.REVERSIBLE,
        change_volume,
        {
            "direction": {"type": "string", "enum": ["up", "down", "mute"]},
            "steps": {"type": "integer", "minimum": 1, "optional": True},
        },
    )
    return registry


def describe(result: ToolResult) -> str:
    if result.data.get("reply"):
        suffix = " [cached]" if result.data.get("cached") else ""
        return f"AKKI: {result.message}{suffix}"
    status = "OK" if result.ok else "FAILED"
    proof = "verified" if result.verified else "unverified"
    suffix = " [cached]" if result.data.get("cached") else ""
    lines = [f"{status} ({proof}){suffix}: {result.message}"]
    matches = result.data.get("matches")
    if matches:
        lines.extend(f"  {entry}" for entry in matches)
    return "\n".join(lines)


MODE_TOGGLE_PATTERN = re.compile(
    r"^(?:hey[\s,]+|ok[\s,]+|okay[\s,]+)?"
    r"(?:(?:akki|aki|akky|aaki|akkii|a key|a ki|key|ki)[\s,]+)?"
    r"(?:change|switch)"
    r"(?:[\s,]+(?:the[\s,]+)?(?:mode|profile))?"
    r"(?:[\s,]+(?:to[\s,]+)?(nsfw|sovereign|guarded|normal|safe|adult))?[.!?]*$",
    re.IGNORECASE,
)

MODE_ALIASES = {
    "nsfw": "nsfw",
    "adult": "nsfw",
    "sovereign": "sovereign",
    "normal": "sovereign",
    "guarded": "guarded",
    "safe": "guarded",
}


def detect_mode_change(text: str) -> str | None:
    match = MODE_TOGGLE_PATTERN.match(" ".join(text.strip().split()))
    if not match:
        return None
    word = (match.group(1) or "").lower()
    return MODE_ALIASES.get(word, "toggle")


def handle(    text: str,
    config: Config,
    registry: ToolRegistry,
    conversation: Conversation | None = None,
    storage: Storage | None = None,
    *,
    confirm: Callable[[str], bool] | None = None,
) -> ToolResult:
    conversation = conversation if conversation is not None else Conversation()
    confirm_action = confirm or (lambda prompt: ask_confirmation(prompt))
    mode_request = detect_mode_change(text)
    if mode_request is not None:
        if mode_request == "toggle":
            mode_request = (
                "sovereign"
                if config.profile.strip().lower() == "nsfw"
                else "nsfw"
            )
        config.profile = mode_request
        save_config(config)
        message = f"Mode set to {mode_request}."
        logger.info("mode changed via voice profile=%s", mode_request)
        conversation.add("user", text)
        conversation.add("assistant", message)
        return ToolResult.success(message, data={"reply": True})
    reminder = parse_reminder(text)
    if reminder is not None:
        if storage is None:
            return ToolResult.failure("Reminders need local storage.")
        seconds, reminder_text = reminder
        job_id = scheduler.schedule_once(
            storage, f"__reminder__: {reminder_text}", seconds
        )
        message = f"Reminder set for {format_duration(seconds)}: {reminder_text}"
        logger.info("reminder scheduled job=%s seconds=%s", job_id, seconds)
        conversation.add("user", text)
        conversation.add("assistant", message)
        return ToolResult.success(
            message, data={"job_id": job_id, "seconds": seconds}
        )
    step_texts = planner.split_steps(text)
    if len(step_texts) > 1:
        requests = planner.plan_steps(text, config)
        if len(requests) == len(step_texts):
            logger.info("route plan steps=%d", len(requests))
            result = planner.execute_steps(
                requests,
                registry,
                profile=config.profile,
                confirm=confirm_action,
                on_result=lambda request, outcome: (
                    conversation.record(request, outcome) if outcome.ok else None
                ),
            )
            logger.info("reply ok=%s verified=%s", result.ok, result.verified)
            conversation.add("user", text)
            conversation.add("assistant", result.message)
            return result
        request = None
    else:
        request = route(text, config)
    if request is None:
        request = resolve_followup(text, conversation)

    if request is None:
        fact = lookup_officeholder(text)
        if fact:
            logger.info("fact lookup answer=%r", fact)
            conversation.add("user", text)
            conversation.add("assistant", fact)
            return ToolResult.success(fact, data={"reply": True})

    if request is not None:
        logger.info("route action tool=%s", request.tool)
        result = registry.execute(
            request,
            profile=config.profile,
            confirm=confirm_action,
        )
        if result.ok:
            conversation.record(request, result)
    else:
        memory = [fact for _, fact in storage.memories()] if storage else None
        learned = storage.recent_feedback(6) if storage else None
        documents = (
            knowledge.document_context(storage, text) if storage is not None else ""
        )
        history = conversation.cloud_messages()
        system = build_system_prompt(
            memory, config.profile, learned, documents, text
        )
        errors: list[str] = []

        def run_tier(
            provider: str,
            model: str,
            call: object,
        ) -> ToolResult | None:
            cache_key = None
            logger.info("llm tier=%s model=%s", provider, model)
            if storage is not None and config.llm.cache_ttl_seconds > 0:
                cache_key = make_cache_key(provider, model, system, history, text)
                hit = storage.cache_get(cache_key)
                if hit is not None and not has_unsupported_script(hit):
                    logger.info("llm cache hit tier=%s model=%s", provider, model)
                    return ToolResult.success(
                        hit, data={"reply": True, "cached": True}
                    )
            outcome = call()
            if outcome.request is not None:
                logger.info(
                    "llm action tier=%s model=%s tool=%s",
                    provider,
                    model,
                    outcome.request.tool,
                )
                executed = registry.execute(
                    outcome.request,
                    profile=config.profile,
                    confirm=confirm_action,
                )
                if executed.ok:
                    conversation.record(outcome.request, executed)
                return executed
            if outcome.text:
                if has_unsupported_script(outcome.text):
                    logger.warning(
                        "llm reply tier=%s model=%s used an unsupported script",
                        provider,
                        model,
                    )
                    errors.append("model replied in an unsupported script")
                    return None
                logger.info(
                    "llm reply tier=%s model=%s text=%r",
                    provider,
                    model,
                    outcome.text[:300],
                )
                if storage is not None and cache_key is not None:
                    storage.cache_put(
                        cache_key, outcome.text, config.llm.cache_ttl_seconds
                    )
                return ToolResult.success(outcome.text, data={"reply": True})
            if outcome.error:
                logger.warning(
                    "llm error tier=%s model=%s: %s",
                    provider,
                    model,
                    outcome.error,
                )
                errors.append(outcome.error)
            return None

        _, cloud_model, _ = resolve_endpoint(config.llm)
        nsfw = config.profile.strip().lower() == "nsfw"
        nsfw_cloud_model = config.llm.nsfw_model if nsfw else ""
        local_model = (
            (config.llm.nsfw_local_model if nsfw else "")
            or config.llm.local_model
            or "richardyoung/fable-qwen2.5-3b-abliterated"
        )
        tiers: list[tuple[str, str, object]] = []
        if config.llm.local_enabled:
            tiers.append(
                (
                    "ollama",
                    local_model,
                    lambda: ask_local(
                        text,
                        registry,
                        config.llm,
                        history=history,
                        memory=memory,
                        profile=config.profile,
                        feedback=learned,
                        documents=documents,
                    ),
                )
            )
        if config.llm.enabled:
            tiers.append(
                (
                    config.llm.provider,
                    nsfw_cloud_model or cloud_model,
                    lambda: ask_cloud(
                        text,
                        registry,
                        config.llm,
                        history=history,
                        memory=memory,
                        profile=config.profile,
                        feedback=learned,
                        documents=documents,
                        model=nsfw_cloud_model or None,
                    ),
                )
            )
        if nsfw_cloud_model:
            if not config.llm.local_first:
                tiers.reverse()
        elif not (config.llm.local_first or nsfw):
            tiers.reverse()

        result = None
        for provider, model, call in tiers:
            result = run_tier(provider, model, call)
            if result is not None:
                break
        if result is None:
            if errors and all(
                error == "model replied in an unsupported script"
                for error in errors
            ):
                result = ToolResult.success(
                    "Sorry, I didn't catch that. Please say it again.",
                    data={"reply": True},
                )
            else:
                result = ToolResult.failure(
                    " | ".join(errors) or "no local or cloud model is available"
                )

    logger.info("reply ok=%s verified=%s", result.ok, result.verified)
    conversation.add("user", text)
    conversation.add("assistant", result.message)
    return result


UNSUPPORTED_SCRIPT_RANGES = (
    (0x0370, 0x03FF),
    (0x0400, 0x04FF),
    (0x0590, 0x05FF),
    (0x0E00, 0x0E7F),
    (0x3040, 0x30FF),
    (0x4E00, 0x9FFF),
    (0xAC00, 0xD7AF),
)


def has_unsupported_script(text: str) -> bool:
    return any(
        start <= ord(char) <= end
        for char in text
        for start, end in UNSUPPORTED_SCRIPT_RANGES
    )


def speak_text(text: str, config: Config) -> None:
    nsfw = config.profile.strip().lower() == "nsfw"
    hindi = _is_devanagari(text) or is_latin_hindi(text)
    if nsfw:
        edge_voice = (
            config.voice.nsfw_hindi_edge_voice
            if hindi
            else config.voice.nsfw_edge_voice
        )
    else:
        edge_voice = (
            config.voice.hindi_edge_voice if hindi else config.voice.edge_voice
        )
    speak(
        text,
        rate=config.voice.rate,
        volume=config.voice.volume,
        voice_name=config.voice.voice_name,
        engine=config.voice.tts_engine,
        piper_voice=config.voice.piper_voice,
        piper_length_scale=config.voice.piper_length_scale,
        piper_speaker=config.voice.piper_speaker,
        pitch=config.voice.tts_pitch,
        edge_voice=edge_voice,
    )


def speak_result(result: ToolResult, config: Config) -> None:
    if not result.message:
        return
    text = result.message
    if len(text) > 400:
        text = text[:400] + "..."
    try:
        speak_text(text, config)
    except VoiceError as exc:
        print(f"voice: {exc}")


def respond(
    text: str,
    config: Config,
    registry: ToolRegistry,
    conversation: Conversation,
    storage: Storage | None,
) -> ToolResult:
    result = handle(text, config, registry, conversation, storage)
    print(describe(result))
    if config.voice.auto_speak:
        speak_result(result, config)
    return result


def print_help() -> None:
    print("Commands:")
    print("  open <app>                 launch an application by name or alias (Start Menu discovery)")
    print("  open <site or URL>         open a website (e.g. open youtube)")
    print("  open <file or folder>      open with the default handler")
    print("  open <project> in <app>    open a file or folder in an app")
    print("  search <terms>             web search")
    print("  find <name>                search configured folders")
    print("  read file <name>           read a local file's text and metadata")
    print("  list files on <folder>     list files with sizes and dates")
    print("  lock screen                lock Windows")
    print("  take a screenshot          save a screen capture")
    print("  increase/decrease volume   change volume")
    print("  remind me in 10 minutes to <task>   set a spoken reminder")
    print("  :tools                     list registered tools")
    print("  :apps [search]             list installed Start Menu and Store apps")
    print("  :alerts                    show mobile alert settings")
    print("  :alerts on|off             enable or disable mobile alerts")
    print("  :alerts check              check important unseen mail now")
    print("  :alerts test               send a test phone notification")
    print("  :alerts topic <topic>      set the ntfy topic")
    print("  :alert <text>              send a manual phone notification")
    print("  :panel                     open the desktop settings window")
    print("  :tray                      show the tray icon state")
    print("  :tray on|off               start or stop the tray icon")
    print("  :widget                      open the desktop access widget")
    print("  :widget on|off             start or stop it and set autostart")
    print("  :shortcut                   create the desktop widget shortcut")
    print("  :mode [sovereign|nsfw|guarded] show or change the content mode")
    print("  say \"akki change\"          toggle between sovereign and nsfw mode")
    print("  :llm                       show the cloud fallback provider")
    print("  :remember <fact>           store a persistent memory")
    print("  :memories                  list stored memories")
    print("  :forget <id>               delete a memory by id")
    print("  :good [note]               reward the last reply")
    print("  :bad [note]                punish the last reply")
    print("  :feedback                  show learned feedback and score")
    print("  :feedback clear            delete all stored feedback")
    print("  :cache                     show response cache stats")
    print("  :cache clear               drop all cached responses")
    print("  :listen                    record a voice command (Enter to stop)")
    print("  :message [text]            copy a message and save a draft")
    print("  :dictate                   record one message, copy it, and save a draft")
    print("  :hotkey                    show the push-to-talk hotkey state")
    print("  :hotkey on|off             enable Ctrl+Space push-to-talk")
    print("  :wake                    show the wake-word state")
    print("  :wake on|off             enable or disable wake-word listening")
    print("  :wake phrase <phrase>    change the wake-word phrase")
    print("  :active [on|off]         keep listening until you say bye akki")
    print("  :speaker                   list enrolled speakers")
    print("  :speaker enroll <name> <audio>   enroll a speaker")
    print("  :speaker forget <name>           forget a speaker")
    print("  :speaker identify <audio>       identify a speaker")
    print("  :camera                       capture a camera frame")
    print("  :face detect <image-b64>      detect faces in an image")
    print("  :face enroll <name> <image>   enroll a face")
    print("  :ui                          show the local web UI state")
    print("  :ui on|off                   start or stop the local web UI")
    print("  :ui port <port>              set the local web UI port")
    print("  :mcp                         show configured MCP servers")
    print("  :mcp reload                  start MCP servers and register tools")
    print("  :mcp stop                    stop MCP servers and unregister tools")
    print("  :stt                       show speech-to-text settings")
    print("  :stt model <name>          switch whisper model, e.g. small")
    print("  :stt language <code|auto>  force recognition language")
    print("  :logs                      show the audit log path")
    print("  :index [path|desktop|all]  index documents for local RAG")
    print("  :ls [folder]               list a folder (default: desktop)")
    print("  :file <file>               read a local file and show details")
    print("  :inspect <file|folder>     read a file or list a folder")
    print("  :docs                      list indexed documents")
    print("  :docs forget <id|path>     remove an indexed document")
    print("  :docs clear                clear the document index")
    print("  :searchdocs <query>        search indexed documents")
    print("  :say <text>                speak text aloud")
    print("  :voice                     show voice settings")
    print("  :voice on|off              toggle spoken replies")
    print("  :voice setup               install the Piper neural voice")
    print("  :voice set <voice-id>      switch Piper voice (downloads if needed)")
    print("  :voice options             list available Piper voices")
    print("  :voice speaker N|auto      pick a speaker for multi-speaker voices")
    print("  :voice use piper|sapi|edge choose the tts engine")
    print("  :voice indian             Indian English neural voice (Edge)")
    print("  :voice indian-female      Indian English female neural voice (Edge)")
    print("  :voice hindi               Hindi neural voice (Edge)")
    print("  :voice hindi-female        Hindi female neural voice (Edge)")
    print("  :voice edge <voice-id>    set a specific Edge neural voice")
    print("  :voice batman             deep Piper neural Batman-style voice")
    print("  :voice pitch <-50..50>    lower or raise voice pitch")
    print("  :voice list                list installed Windows voices")
    print("  :clear                     clear conversation context")
    print("  :db                        show the database path")
    print("  :config                    show the config path")
    print("  :quit                      exit")
    print("Unmatched requests go to the cloud fallback when its API key is set.")


def run_once(
    text: str,
    config: Config,
    registry: ToolRegistry,
    storage: Storage | None = None,
    *,
    speak_reply: bool = False,
) -> int:
    result = handle(text, config, registry, storage=storage)
    print(describe(result))
    if speak_reply:
        speak_result(result, config)
    return 0 if result.ok else 1


def repl(
    config: Config,
    registry: ToolRegistry,
    storage: Storage | None = None,
    config_file: Path | None = None,
    *,
    start_ui: bool = False,
    start_tray: bool = False,
    start_panel: bool = False,
    start_widget: bool = False,
    widget_only: bool = False,
    headless: bool = False,
    secrets_store: SecretsStore | None = None,
) -> int:
    print(BANNER.format(version=__version__))
    session_id = storage.start_session() if storage is not None else None
    conversation = Conversation(
        on_turn=(
            (lambda role, content: storage.add_turn(session_id, role, content))
            if storage is not None and session_id is not None
            else None
        )
    )

    def persist() -> None:
        if config_file is None:
            return
        try:
            save_config(config, config_file)
        except OSError as exc:
            print(f"could not save config: {exc}")

    pending: queue.Queue[str] = queue.Queue()
    hotkey_state: dict[str, object] = {"listener": None, "capture": None, "stop": None}
    wake_state: dict[str, object] = {
        "listener": None,
        "hotkey_started_by_wake": False,
        "conversation": False,
    }
    ui_state: dict[str, object] = {"ui": None}
    mcp_state: dict[str, object] = {"manager": None}
    panel_state: dict[str, object] = {"panel": None}
    tray_state: dict[str, object] = {"tray": None}
    widget_state: dict[str, object] = {"widget": None}
    secrets_state: dict[str, object] = {"store": secrets_store}
    indicator = ListeningIndicator(
        enabled=lambda: config.desktop.bubble_enabled
    )
    indicator.warm_up()

    def respond_visible(text: str) -> None:
        indicator.show("thinking", sound=False)
        try:
            respond(
                text,
                config=config,
                registry=registry,
                conversation=conversation,
                storage=storage,
            )
        finally:
            indicator.hide()

    web_conversation = Conversation()
    web_lock = threading.Lock()

    def open_settings_panel() -> None:
        current = panel_state.get("panel")
        if isinstance(current, SettingsPanel) and current.active:
            print("settings panel already open")
            return
        panel = SettingsPanel(
            config,
            config_file=config_file,
            on_save=lambda new: apply_config(config, new),
        )
        panel.start()
        panel_state["panel"] = panel
        logger.info("settings panel opened")

    def start_tray_icon(*, announce: bool = True) -> bool:
        current = tray_state.get("tray")
        if isinstance(current, TrayIcon) and current.active:
            if announce:
                print("tray already running")
            return True
        if not tray_supported():
            print("tray support needs pystray and pillow: pip install -e .[desktop]")
            return False
        tray = TrayIcon(
            open_settings_panel, on_widget=open_desktop_widget
        )
        try:
            tray.start()
        except TrayError as exc:
            print(f"tray: {exc}")
            return False
        tray_state["tray"] = tray
        if announce:
            print("tray icon running; open settings from the tray menu")
        return True

    def stop_tray_icon() -> None:
        current = tray_state.get("tray")
        if isinstance(current, TrayIcon):
            current.stop()
        tray_state["tray"] = None

    def open_desktop_widget(*, announce: bool = True) -> bool:
        current = widget_state.get("widget")
        if isinstance(current, DesktopWidget) and current.active:
            if announce:
                print("desktop widget already open")
            return True
        store = secrets_state.get("store")
        if not isinstance(store, SecretsStore):
            store = SecretsStore()
            store.load_into_env()
            secrets_state["store"] = store
        widget = DesktopWidget(
            config,
            secrets=store,
            config_file=config_file,
            on_save=lambda new: apply_config(config, new),
            on_listen=on_hotkey,
            on_open_settings=open_settings_panel,
            on_test_alert=lambda: alerts.send_ntfy(
                config.alerts,
                "AKKI test",
                "Mobile alerts are working.",
            ),
        )
        widget.start()
        widget_state["widget"] = widget
        if announce:
            print("desktop widget opened")
        return True

    def stop_desktop_widget() -> None:
        current = widget_state.get("widget")
        if isinstance(current, DesktopWidget):
            current.stop()
        widget_state["widget"] = None

    def stop_capture() -> None:
        stop = hotkey_state.get("stop")
        if isinstance(stop, threading.Event):
            stop.set()

    def capture_voice() -> None:
        stop_event = threading.Event()
        hotkey_state["stop"] = stop_event
        logger.info("hotkey capture started")
        print(
            "\r[mic] listening... press Ctrl+Space again to stop",
            flush=True,
        )
        indicator.show()
        audio_path: Path | None = None
        try:
            transcript, audio_path = capture_push(
                config.voice.stt_model,
                config.voice.stt_language,
                stop_event=stop_event,
                keep_audio=True,
            )
        except VoiceError as exc:
            print(f"\r[mic] {exc}", flush=True)
            pending.put("")
        except Exception as exc:
            logger.exception("hotkey capture failed")
            print(f"\r[mic] capture failed: {exc}", flush=True)
            pending.put("")
        else:
            speaker_info = None
            if storage is not None:
                try:
                    speaker_info = speaker.identify_speaker(storage, audio_path)
                except Exception as exc:
                    logger.warning("speaker identification failed: %s", exc)
            pending.put(transcript)
            logger.info("hotkey transcript=%r", transcript)
            if speaker_info is not None:
                print(
                    f"[speaker] {speaker_info['speaker']} "
                    f"(similarity={speaker_info['similarity']:.2f})"
                )
        finally:
            logger.info("hotkey capture finished")
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)
            indicator.hide()
            hotkey_state["stop"] = None
            hotkey_state["capture"] = None
            if wake_state.get("hotkey_started_by_wake") and not wake_state.get(
                "conversation"
            ):
                start_wake(announce=False)

    def is_farewell(text: str) -> bool:
        cleaned = " ".join(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())
        if not cleaned:
            return False
        for phrase in (
            "bye akki",
            "goodbye akki",
            "by akki",
            "buy akki",
            "stop listening",
            "good bye akki",
        ):
            if phrase in cleaned:
                return True
        words = cleaned.split()
        return "bye" in words or "goodbye" in words or cleaned == "good bye"

    def say_goodbye() -> None:
        print("AKKI: Goodbye.")
        if config.voice.auto_speak:
            try:
                speak_text("Goodbye.", config)
            except VoiceError as exc:
                print(f"voice: {exc}")

    def conversation_loop() -> None:
        logger.info("conversation loop started")
        try:
            while wake_state.get("conversation"):
                stop_event = threading.Event()
                hotkey_state["stop"] = stop_event
                print(
                    "\r[mic] listening... say 'bye akki' to stop",
                    flush=True,
                )
                indicator.show()
                try:
                    transcript, _audio_path = capture_push(
                        config.voice.stt_model,
                        config.voice.stt_language,
                        stop_event=stop_event,
                    )
                except VoiceError:
                    continue
                except Exception as exc:
                    logger.exception("conversation capture failed")
                    print(f"\r[mic] capture failed: {exc}", flush=True)
                    continue
                finally:
                    hotkey_state["stop"] = None
                transcript = (transcript or "").strip()
                if not transcript:
                    continue
                print(f"[mic] heard: {transcript}")
                logger.info("conversation transcript=%r", transcript)
                if is_farewell(transcript):
                    logger.info("conversation farewell")
                    say_goodbye()
                    break
                try:
                    respond_visible(transcript)
                except Exception as exc:
                    logger.exception("conversation respond failed")
                    print(f"\r[mic] respond failed: {exc}", flush=True)
                time.sleep(0.25)
        finally:
            logger.info("conversation loop ended")
            hotkey_state["capture"] = None
            wake_state["conversation"] = False
            indicator.hide()
            if config.voice.wake_enabled:
                start_wake(announce=False)

    def on_hotkey() -> None:
        logger.info("hotkey pressed")
        worker = hotkey_state.get("capture")
        if isinstance(worker, threading.Thread) and worker.is_alive():
            stop_capture()
            return
        worker = threading.Thread(
            target=capture_voice, name="akki-capture", daemon=True
        )
        hotkey_state["capture"] = worker
        worker.start()

    def stop_hotkey() -> None:
        stop_capture()
        listener = hotkey_state.get("listener")
        if isinstance(listener, HotkeyListener):
            listener.stop()
        hotkey_state["listener"] = None

    def start_hotkey(*, announce: bool = True) -> None:
        current = hotkey_state.get("listener")
        if isinstance(current, HotkeyListener) and current.active:
            if announce:
                print(f"hotkey already on ({config.voice.hotkey})")
            return
        if not hotkey_supported():
            print("global hotkeys are only available on Windows")
            return
        try:
            listener = HotkeyListener(on_hotkey, config.voice.hotkey)
            listener.start()
        except HotkeyError as exc:
            print(f"hotkey: {exc}")
            logger.warning("hotkey registration failed: %s", exc)
            config.voice.hotkey_enabled = False
            persist()
            return
        hotkey_state["listener"] = listener
        config.voice.hotkey_enabled = True
        persist()
        logger.info("hotkey enabled=%s", config.voice.hotkey)
        if announce:
            print(
                f"hotkey on: {config.voice.hotkey} "
                "(press once to talk, again to stop)"
            )

    def start_conversation(*, from_wake: bool = False) -> None:
        if wake_state.get("conversation"):
            return
        worker = hotkey_state.get("capture")
        if isinstance(worker, threading.Thread) and worker.is_alive():
            return
        listener = wake_state.get("listener")
        wake_was_active = isinstance(listener, WakeWordListener) and listener.active
        if not from_wake and wake_was_active:
            listener.stop()
            wake_state["listener"] = None
        wake_state["conversation"] = True
        worker = threading.Thread(
            target=conversation_loop, name="akki-conversation", daemon=True
        )
        hotkey_state["capture"] = worker
        worker.start()
        logger.info("conversation started from_wake=%s", from_wake)

    def on_wake_detected() -> None:
        start_conversation(from_wake=True)

    def stop_wake() -> None:
        listener = wake_state.get("listener")
        if isinstance(listener, WakeWordListener):
            listener.stop()
        wake_state["listener"] = None
        wake_state["conversation"] = False
        wake_was_on = bool(wake_state.get("hotkey_started_by_wake"))
        wake_state["hotkey_started_by_wake"] = False
        stop_capture()
        if wake_was_on:
            stop_hotkey()

    def start_wake(*, announce: bool = True) -> None:
        current = wake_state.get("listener")
        if isinstance(current, WakeWordListener) and current.active:
            if announce:
                print(f"wake already on ({current.phrase})")
            return
        if not wake_supported():
            print("wake-word listening is only available on Windows")
            return
        try:
            listener = WakeWordListener(
                on_wake_detected,
                phrase=config.voice.wake_word,
                model_size=config.voice.stt_model,
                language=config.voice.stt_language,
            )
            listener.start()
        except WakeWordError as exc:
            print(f"wake: {exc}")
            logger.warning("wake registration failed: %s", exc)
            return
        wake_state["listener"] = listener
        logger.info("wake enabled=%s", listener.phrase)
        hotkey_was_active = (
            isinstance(hotkey_state.get("listener"), HotkeyListener)
            and hotkey_state.get("listener").active
        )
        start_hotkey(announce=False)
        if not hotkey_was_active:
            wake_state["hotkey_started_by_wake"] = True
        if announce:
            print(f"wake on: {listener.phrase} (detect before capture)")

    def web_status() -> dict[str, object]:
        _, model, _ = resolve_endpoint(config.llm)
        return {
            "version": __version__,
            "profile": config.profile,
            "model": model,
            "local_model": config.llm.local_model,
            "local_enabled": config.llm.local_enabled,
        }

    def web_tools() -> list[dict[str, object]]:
        return [
            {
                "name": spec.name,
                "level": spec.level.value,
                "description": spec.description,
            }
            for spec in registry.specs()
        ]

    def web_chat(text: str) -> dict[str, object]:
        local_storage = Storage(storage.path) if storage is not None else None
        try:
            with web_lock:
                result = handle(
                    text,
                    config,
                    registry,
                    web_conversation,
                    local_storage,
                    confirm=lambda _: False,
                )
            return {
                "ok": result.ok,
                "verified": result.verified,
                "message": result.message,
                "data": result.data,
            }
        finally:
            if local_storage is not None:
                local_storage.close()

    def start_webui(*, announce: bool = True) -> None:
        current = ui_state.get("ui")
        if isinstance(current, WebUI) and current.active:
            if announce:
                print(f"web ui already on: {current.url}")
            return
        ui = WebUI(
            web_chat,
            host=config.web.host,
            port=config.web.port,
            status=web_status,
            tools=web_tools,
        )
        try:
            url = ui.start()
        except WebUIError as exc:
            print(f"web ui: {exc}")
            logger.warning("web ui failed: %s", exc)
            return
        ui_state["ui"] = ui
        config.web.enabled = True
        persist()
        logger.info("web ui enabled=%s", url)
        if announce:
            print(f"web ui on: {url}")

    def stop_webui() -> None:
        ui = ui_state.get("ui")
        if isinstance(ui, WebUI):
            ui.stop()
        ui_state["ui"] = None

    def start_mcp(*, announce: bool = True) -> None:
        current = mcp_state.get("manager")
        if isinstance(current, MCPManager):
            current.close(registry)
        manager = MCPManager(config.mcp_servers)
        errors = manager.start(registry)
        mcp_state["manager"] = manager
        if announce:
            if not config.mcp_servers:
                print("no MCP servers configured")
            else:
                print(f"mcp tools registered={len(manager.registered_names)}")
            for error in errors:
                print(f"mcp: {error}")
        logger.info(
            "mcp servers=%d tools=%d",
            len(manager.clients),
            len(manager.registered_names),
        )

    def stop_mcp() -> None:
        manager = mcp_state.get("manager")
        if isinstance(manager, MCPManager):
            manager.close(registry)
        mcp_state["manager"] = None

    def read_line(prompt: str) -> tuple[str, bool]:
        listener = hotkey_state.get("listener")
        if not isinstance(listener, HotkeyListener) or not listener.active:
            return input(prompt), False
        if not sys.stdin.isatty():
            return input(prompt), False
        try:
            import msvcrt
        except ImportError:
            return input(prompt), False
        sys.stdout.write(prompt)
        sys.stdout.flush()
        chars: list[str] = []
        while True:
            if not pending.empty():
                sys.stdout.write("\n")
                sys.stdout.flush()
                return pending.get(), True
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in {"\r", "\n"}:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(chars), False
                if char == "\x03":
                    raise KeyboardInterrupt
                if char == "\x08":
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if char in {"\x00", "\xe0"}:
                    msvcrt.getwch()
                    continue
                if char >= " ":
                    chars.append(char)
                    sys.stdout.write(char)
                    sys.stdout.flush()
                continue
            time.sleep(0.05)

    def record_feedback(rating: int, note: str) -> None:
        prompt, response = conversation.last_exchange()
        if not response:
            print("there is no reply to rate yet")
            return
        label = "reward" if rating > 0 else "punishment"
        if storage is None:
            print(f"{label} noted for this session only (database disabled)")
            return
        storage.add_feedback(
            rating,
            note=note,
            prompt=prompt,
            response=response,
            session_id=session_id,
        )
        stats = storage.feedback_stats()
        logger.info("feedback rating=%+d note_len=%d", rating, len(note))
        sign = "+1" if rating > 0 else "-1"
        print(f"{label} recorded ({sign}); score {stats['score']:+d}")

    def show_feedback() -> None:
        if storage is None:
            print("feedback needs the database; start AKKI without --no-db")
            return
        stats = storage.feedback_stats()
        print(
            f"score {stats['score']:+d} "
            f"rewards={stats['positive']} punishments={stats['negative']} "
            f"total={stats['total']}"
        )
        for item in storage.recent_feedback(6):
            sign = "+" if int(item["rating"]) > 0 else "-"
            note = item["note"] or "(no note)"
            snippet = " ".join(str(item["response"]).split())[:80]
            print(f" {sign} {note}: {snippet}")

    if config.voice.hotkey_enabled:
        start_hotkey(announce=False)
    if config.voice.wake_enabled and not config.voice.conversation_mode:
        start_wake(announce=False)
    if config.voice.conversation_mode:
        start_conversation()
    if config.web.enabled or start_ui:
        start_webui(announce=False)
    if config.desktop.tray_enabled or start_tray:
        start_tray_icon(announce=False)
    if start_panel:
        open_settings_panel()
    if config.desktop.widget_enabled or start_widget or widget_only:
        open_desktop_widget(announce=False)

    scheduler_stop = threading.Event()
    scheduler_thread: threading.Thread | None = None

    def scheduler_loop() -> None:
        while not scheduler_stop.is_set():
            time.sleep(0.5)
            if storage is None:
                break
            loop_storage = Storage(storage.path)
            try:
                now = time.time()
                scheduler.execute_due(loop_storage, registry, config, now)
            finally:
                loop_storage.close()

    scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    scheduler_thread.start()

    alerts_stop = threading.Event()
    alerts_thread: threading.Thread | None = None

    def alerts_loop() -> None:
        while not alerts_stop.is_set():
            if (
                storage is None
                or not config.alerts.enabled
                or not config.alerts.imap_host
                or not config.alerts.ntfy_topic
            ):
                alerts_stop.wait(5)
                continue
            loop_storage = Storage(storage.path)
            try:
                sent = alerts.poll_once(loop_storage, config)
                if sent:
                    logger.info("mobile alerts sent=%d", len(sent))
            except alerts.AlertError as exc:
                logger.warning("mobile alert poll failed: %s", exc)
            except Exception:
                logger.exception("mobile alert poll crashed")
            finally:
                loop_storage.close()
            alerts_stop.wait(max(10.0, float(config.alerts.poll_seconds)))

    alerts_thread = threading.Thread(target=alerts_loop, daemon=True)
    alerts_thread.start()

    if headless:
        logger.info("headless mode active")
        try:
            while True:
                try:
                    text = pending.get(timeout=0.5).strip()
                except queue.Empty:
                    continue
                if not text:
                    continue
                if text in {":quit", ":exit", ":q"}:
                    break
                print(f"[mic] heard: {text}")
                respond_visible(text)
                start_conversation()
        except KeyboardInterrupt:
            pass
        stop_hotkey()
        stop_wake()
        return 0

    if widget_only:
        widget = widget_state.get("widget")
        try:
            while isinstance(widget, DesktopWidget) and widget.active:
                try:
                    text = pending.get(timeout=0.25).strip()
                except queue.Empty:
                    continue
                if not text:
                    continue
                if text in {":quit", ":exit", ":q"}:
                    break
                respond_visible(text)
                start_conversation()
        except KeyboardInterrupt:
            pass
        stop_hotkey()
        stop_wake()
        stop_webui()
        stop_mcp()
        scheduler_stop.set()
        alerts_stop.set()
        if scheduler_thread is not None and scheduler_thread.is_alive():
            scheduler_thread.join(2)
        if alerts_thread is not None and alerts_thread.is_alive():
            alerts_thread.join(2)
        stop_tray_icon()
        stop_desktop_widget()
        indicator.stop()
        return 0

    while True:
        try:
            raw, via_voice = read_line("akki> ")
            text = raw.strip()
        except (EOFError, KeyboardInterrupt):
            print()
            stop_hotkey()
            stop_wake()
            stop_webui()
            stop_mcp()
            scheduler_stop.set()
            if scheduler_thread is not None and scheduler_thread.is_alive():
                scheduler_thread.join(2)
            alerts_stop.set()
            if alerts_thread is not None and alerts_thread.is_alive():
                alerts_thread.join(2)
            stop_tray_icon()
            stop_desktop_widget()
            indicator.stop()
            return 0
        if via_voice and text:
            print(f"[mic] heard: {text}")
        if not text:
            continue
        if text in {":quit", ":exit", ":q"}:
            stop_hotkey()
            stop_wake()
            stop_webui()
            stop_mcp()
            scheduler_stop.set()
            if scheduler_thread is not None and scheduler_thread.is_alive():
                scheduler_thread.join(2)
            alerts_stop.set()
            if alerts_thread is not None and alerts_thread.is_alive():
                alerts_thread.join(2)
            stop_tray_icon()
            stop_desktop_widget()
            indicator.stop()
            return 0
        if text == ":help":
            print_help()
            continue
        if text == ":tools":
            for spec in registry.specs():
                print(f"  {spec.name:<12} {spec.level.value:<10} {spec.description}")
            continue
        if text == ":apps" or text.startswith(":apps "):
            query = text[len(":apps") :].strip()
            discovered = list_apps(query, refresh=True)
            if not discovered:
                print("no Start Menu or Store apps found")
                continue
            for app in discovered:
                print(f"  {app['name']}")
            print(f"  {len(discovered)} app(s)")
            continue
        if text == ":alerts":
            settings = config.alerts
            state = "on" if settings.enabled else "off"
            print(f"mobile alerts: {state}")
            print(
                f"  ntfy: {settings.ntfy_server or '(not set)'} "
                f"topic={settings.ntfy_topic or '(not set)'}"
            )
            print(
                f"  imap: {settings.imap_user or '(not set)'}"
                f"@{settings.imap_host or '(not set)'}:{settings.imap_port} "
                f"folder={settings.imap_folder}"
            )
            print(
                f"  threshold={settings.importance_threshold:.2f} "
                f"poll={settings.poll_seconds:.0f}s "
                f"password_env={settings.imap_password_env}"
            )
            if storage is not None:
                recent = storage.recent_alerts(5)
                if recent:
                    print("  recent:")
                    for item in recent:
                        mark = "sent" if int(item["sent"]) else "skip"
                        print(
                            f"    {mark} {float(item['importance']):.2f} "
                            f"{item['title']}"
                        )
            continue
        if text in {":alerts on", ":alerts off"}:
            config.alerts.enabled = text.endswith(" on")
            save_config(config)
            if config.alerts.enabled:
                print("mobile alerts on")
                if not config.alerts.ntfy_topic or not config.alerts.imap_host:
                    print("set the ntfy topic and IMAP host in :panel to start checking")
            else:
                print("mobile alerts off")
            continue
        if text.startswith(":alerts topic "):
            config.alerts.ntfy_topic = text[len(":alerts topic ") :].strip()
            save_config(config)
            print(f"ntfy topic set to {config.alerts.ntfy_topic or '(empty)'}")
            continue
        if text == ":alerts test":
            result = alerts.send_ntfy(
                config.alerts, "AKKI test", "Mobile alerts are working."
            )
            print(result.message)
            continue
        if text == ":alerts check":
            if storage is None:
                print("mobile alerts need the database")
                continue
            try:
                sent = alerts.poll_once(storage, config)
            except alerts.AlertError as exc:
                print(f"alerts: {exc}")
                continue
            if not sent:
                print("no new important mail")
                continue
            for item in sent:
                print(f"  sent {float(item['importance']):.2f} {item['title']}")
            continue
        if text.startswith(":alert "):
            body = text[len(":alert ") :].strip()
            result = alerts.send_ntfy(config.alerts, "AKKI", body)
            print(result.message)
            continue
        if text == ":panel":
            open_settings_panel()
            continue
        if text == ":tray":
            current = tray_state.get("tray")
            running = isinstance(current, TrayIcon) and current.active
            available = tray_supported()
            print(
                f"tray: {'on' if running else 'off'} "
                f"(support: {'available' if available else 'missing'})"
            )
            if not available:
                print("install tray support with pip install -e .[desktop]")
            continue
        if text in {":tray on", ":tray off"}:
            if text.endswith(" on"):
                enabled = start_tray_icon()
            else:
                stop_tray_icon()
                enabled = False
            config.desktop.tray_enabled = enabled
            persist()
            continue
        if text == ":widget" or text in {":widget on", ":widget off"}:
            if text == ":widget off":
                stop_desktop_widget()
                config.desktop.widget_enabled = False
                persist()
                print("desktop widget off")
            else:
                open_desktop_widget()
                if text == ":widget on":
                    config.desktop.widget_enabled = True
                    persist()
            continue
        if text.startswith(":shortcut"):
            result = install_desktop_widget_shortcut()
            print(result.message)
            continue
        if text == ":mode" or text.startswith(":mode "):
            requested = text[len(":mode") :].strip().lower()
            if not requested:
                print(f"mode: {config.profile}")
                continue
            if requested not in {"sovereign", "nsfw", "guarded"}:
                print("usage: :mode sovereign|nsfw|guarded")
                continue
            config.profile = requested
            persist()
            print(f"mode set to {requested}")
            continue
        if text == ":config":
            print(config_path())
            continue
        if text == ":logs":
            print(log_path())
            continue
        if text == ":index" or text.startswith(":index "):
            if storage is None:
                print("document indexing needs the database")
                continue
            raw_target = text[len(":index") :].strip()
            if raw_target:
                key = raw_target.lower()
                if key in {"all", "everything"} or key in {
                    "desktop", "documents", "downloads", "projects", "code", "dev"
                }:
                    targets = resolve_targets(key, config)
                else:
                    targets = [Path(raw_target).expanduser()]
            else:
                targets = list(config.search_roots)
            total_indexed = 0
            total_skipped = 0
            for target in targets:
                def progress(number: int, path: str) -> None:
                    if number % 25 == 0:
                        print(f"  indexing {number}: {Path(path).name}")

                try:
                    indexed, skipped = knowledge.index_path(
                        storage, target, progress=progress
                    )
                except knowledge.KnowledgeError as exc:
                    print(f"index: {exc}")
                    continue
                total_indexed += indexed
                total_skipped += skipped
                print(f"  {target}: {indexed} indexed, {skipped} skipped")
            print(
                f"indexed {total_indexed} file(s), skipped {total_skipped}"
            )
            logger.info("indexed=%d skipped=%d", total_indexed, total_skipped)
            continue
        if text == ":docs":
            if storage is None:
                print("document index needs the database")
                continue
            entries = knowledge.list_documents(storage)
            if not entries:
                print("no indexed documents; use :index <path>")
            for entry in entries[:80]:
                print(
                    f"  #{entry['id']:<3} {entry['chunks']:>3} chunks  "
                    f"{entry['path']}"
                )
            if len(entries) > 80:
                print(f"  ... {len(entries) - 80} more")
            continue
        if text.startswith(":docs forget "):
            if storage is None:
                print("document index needs the database")
                continue
            value = text[len(":docs forget ") :].strip()
            removed = knowledge.remove_document(storage, value)
            print("removed" if removed else "no matching document")
            continue
        if text == ":docs clear":
            if storage is None:
                print("document index needs the database")
                continue
            removed = knowledge.clear_documents(storage)
            print(f"cleared {removed} document(s)")
            continue
        if text == ":ls" or text.startswith(":ls "):
            raw_target = text[len(":ls") :].strip() or "desktop"
            result = registry.execute(
                ActionRequest("list_folder", {"target": raw_target}, text),
                profile=config.profile,
            )
            print(describe(result))
            continue
        if text.startswith(":file "):
            target = text[len(":file ") :].strip()
            if not target:
                print("usage: :file <file>")
                continue
            result = registry.execute(
                ActionRequest("read_file", {"target": target}, text),
                profile=config.profile,
            )
            print(describe(result))
            continue
        if text.startswith(":inspect "):
            target = text[len(":inspect ") :].strip()
            if not target:
                print("usage: :inspect <file|folder>")
                continue
            result = registry.execute(
                ActionRequest("inspect_path", {"target": target}, text),
                profile=config.profile,
            )
            print(describe(result))
            continue
        if text.startswith(":searchdocs "):
            if storage is None:
                print("document index needs the database")
                continue
            query = text[len(":searchdocs ") :].strip()
            hits = knowledge.search(storage, query)
            if not hits:
                print("no document matches")
            for hit in hits:
                snippet = str(hit["text"])[:160]
                print(f"  {hit['path']}\n    {snippet}")
            continue
        if text == ":read" or text.startswith(":read "):
            url = text[len(":read ") :].strip() if text.startswith(":read ") else ""
            if not url:
                print("usage: :read <url>")
                continue
            result = registry.execute(ActionRequest("read_url", {"url": url}, text))
            if not result.ok:
                print(describe(result))
                continue
            page_text = str(result.data.get("text") or result.message)
            respond(
                f"Summarize the following web page and answer the user's request: {page_text}",
                config,
                registry,
                conversation,
                storage,
            )
            continue
        if text == ":hotkey":
            listener = hotkey_state.get("listener")
            active = isinstance(listener, HotkeyListener) and listener.active
            capture = hotkey_state.get("capture")
            listening = isinstance(capture, threading.Thread) and capture.is_alive()
            print(
                f"hotkey={config.voice.hotkey} "
                f"supported={hotkey_supported()} "
                f"active={'yes' if active else 'no'} "
                f"listening={'yes' if listening else 'no'} "
                f"autostart={'on' if config.voice.hotkey_enabled else 'off'}"
            )
            continue
        if text == ":hotkey on":
            start_hotkey()
            continue
        if text == ":hotkey off":
            stop_hotkey()
            config.voice.hotkey_enabled = False
            persist()
            if wake_state.get("hotkey_started_by_wake"):
                stop_wake()
            logger.info("hotkey disabled")
            print("hotkey off")
            continue
        if text == ":stt":
            print(
                f"model={config.voice.stt_model} "
                f"language={config.voice.stt_language}"
            )
            continue
        if text.startswith(":stt model "):
            model = text[len(":stt model ") :].strip()
            if not model or " " in model:
                print("usage: :stt model small|base|medium|base.en")
                continue
            config.voice.stt_model = model
            persist()
            logger.info("stt model=%s", model)
            print(f"stt model set to {model} (downloaded on first use)")
            continue
        if text.startswith(":stt language "):
            language = text[len(":stt language ") :].strip().lower()
            if not language:
                print("usage: :stt language auto|en|hi|mr")
                continue
            config.voice.stt_language = language
            persist()
            logger.info("stt language=%s", language)
            print(f"stt language set to {language}")
            continue
        if text.startswith(":schedule every ") or text.startswith(":schedule daily "):
            mode_and_rest = text[len(":schedule ") :].split(" ", 1)
            mode = mode_and_rest[0] if mode_and_rest else ""
            rest = mode_and_rest[1] if len(mode_and_rest) > 1 else ""
            if mode.lower() == "every":
                match = re.fullmatch(r"every ([0-9]+(?:\.[0-9]+)?) (.+)", rest, re.IGNORECASE)
                if not match:
                    print("usage: :schedule every <seconds> <command>")
                    continue
                seconds = float(match.group(1))
                command_text = match.group(2).strip()
                job_id = scheduler.schedule_every(storage, command_text, seconds)
                print(f"scheduled job #{job_id}: every {seconds}s -> {command_text}")
                continue
            if mode.lower() == "daily":
                match = re.fullmatch(r"daily ([0-9]{2}:[0-9]{2}) (.+)", rest, re.IGNORECASE)
                if not match:
                    print("usage: :schedule daily <HH:MM> <command>")
                    continue
                hhmm = match.group(1)
                command_text = match.group(2).strip()
                job_id = scheduler.schedule_daily(storage, command_text, hhmm)
                print(f"scheduled job #{job_id}: daily {hhmm} -> {command_text}")
                continue
        if text == ":schedules":
            if storage is None:
                print("schedules need the database")
                continue
            jobs = scheduler.list_jobs(storage)
            if not jobs:
                print("no scheduled jobs")
            for job in jobs:
                print(
                    f"  #{job.get('id')} kind={job.get('kind')} "
                    f"next_run={job.get('next_run')} enabled={job.get('enabled')} "
                    f"{job.get('command')}"
                )
            continue
        if text.startswith(":schedule cancel "):
            if storage is None:
                print("schedules need the database")
                continue
            job_id = int(text[len(":schedule cancel ") :].strip())
            removed = scheduler.cancel_job(storage, job_id)
            print("cancelled" if removed else f"no job #{job_id}")
            continue
        if text == ":wake":
            listener = wake_state.get("listener")
            wake_active = isinstance(listener, WakeWordListener) and listener.active
            print(
                f"wake={config.voice.wake_word} "
                f"supported={wake_supported()} "
                f"active={'yes' if wake_active else 'no'}"
            )
            continue
        if text == ":wake on":
            start_wake()
            continue
        if text == ":wake off":
            stop_wake()
            config.voice.wake_enabled = False
            persist()
            logger.info("wake disabled")
            print("wake off")
            continue
        if text.startswith(":wake phrase "):
            phrase = text[len(":wake phrase ") :].strip()
            if not phrase:
                print("usage: :wake phrase <phrase>")
                continue
            config.voice.wake_word = phrase
            persist()
            logger.info("wake phrase=%s", phrase)
            print(f"wake phrase set to {phrase}")
            continue
        if text == ":active":
            active = bool(wake_state.get("conversation"))
            print(f"conversation mode: {'on' if active else 'off'}")
            continue
        if text in {":active on", ":active off"}:
            want = text.endswith(" on")
            config.voice.conversation_mode = want
            persist()
            if want:
                start_conversation()
            else:
                wake_state["conversation"] = False
                stop_capture()
            logger.info("conversation mode=%s", want)
            print(f"conversation mode {'on' if want else 'off'}")
            continue
        if text == ":speaker":
            if storage is None:
                print("speaker recognition needs the database")
                continue
            entries = speaker.list_speakers(storage)
            if not entries:
                print("no enrolled speakers")
            for entry in entries:
                print(f"  #{entry['id']} {entry['name']}")
            continue
        if text.startswith(":speaker enroll "):
            parts = text[len(":speaker enroll ") :].strip().split(" ", 1)
            if len(parts) != 2:
                print("usage: :speaker enroll <name> <audio-path>")
                continue
            name, audio_path = parts
            if storage is None:
                print("speaker recognition needs the database")
                continue
            speaker_id = speaker.enroll_speaker(storage, name, audio_path)
            print(f"enrolled speaker #{speaker_id}: {name}")
            continue
        if text.startswith(":speaker forget "):
            name = text[len(":speaker forget ") :].strip()
            if not name:
                print("usage: :speaker forget <name>")
                continue
            if storage is None:
                print("speaker recognition needs the database")
                continue
            removed = speaker.forget_speaker(storage, name)
            print("removed" if removed else f"no speaker #{name}")
            continue
        if text.startswith(":speaker identify "):
            audio_path = text[len(":speaker identify ") :].strip()
            if not audio_path:
                print("usage: :speaker identify <audio-path>")
                continue
            if storage is None:
                print("speaker recognition needs the database")
                continue
            info = speaker.identify_speaker(storage, audio_path)
            if info is None:
                print("no speaker matched")
            else:
                print(f"{info['speaker']} (similarity={info['similarity']:.2f})")
            continue
        if text == ":camera":
            result = capture_camera()
            if result.ok:
                print(f"camera captured {result.data.get('width')}x{result.data.get('height')}")
            else:
                print(result.message)
            continue
        if text.startswith(":face detect "):
            image_b64 = text[len(":face detect ") :].strip()
            if not image_b64:
                print("usage: :face detect <image-b64>")
                continue
            faces = vision.detect_faces(image_b64)
            if not faces:
                print("no faces detected")
            for face in faces:
                print(
                    f"  face at x={face['x']} y={face['y']} "
                    f"w={face['width']} h={face['height']}"
                )
            continue
        if text.startswith(":face enroll "):
            parts = text[len(":face enroll ") :].strip().split(" ", 1)
            if len(parts) != 2:
                print("usage: :face enroll <name> <image-b64>")
                continue
            name, image_b64 = parts
            if storage is None:
                print("face recognition needs the database")
                continue
            face_id = vision.enroll_face(storage, name, image_b64)
            print(f"enrolled face #{face_id}: {name}")
            continue
        if text == ":mcp":
            manager = mcp_state.get("manager")
            if not config.mcp_servers:
                print("no MCP servers configured")
            for name, settings in config.mcp_servers.items():
                running = (
                    isinstance(manager, MCPManager)
                    and name in manager.clients
                )
                print(
                    f"  {name}: "
                    f"{'enabled' if settings.enabled else 'disabled'} "
                    f"{'running' if running else 'stopped'}"
                )
            if isinstance(manager, MCPManager):
                for name in manager.registered_names:
                    print(f"  tool {name}")
            continue
        if text in {":mcp reload", ":mcp start"}:
            start_mcp()
            continue
        if text == ":mcp stop":
            stop_mcp()
            print("mcp stopped")
            continue
        if text == ":ui":
            current = ui_state.get("ui")
            active = isinstance(current, WebUI) and current.active
            url = current.url if active else f"http://{config.web.host}:{config.web.port}/"
            print(
                f"web ui host={config.web.host} port={config.web.port} "
                f"active={'yes' if active else 'no'} "
                f"autostart={'on' if config.web.enabled else 'off'} "
                f"url={url}"
            )
            continue
        if text == ":ui on":
            start_webui()
            continue
        if text == ":ui off":
            stop_webui()
            config.web.enabled = False
            persist()
            logger.info("web ui disabled")
            print("web ui off")
            continue
        if text.startswith(":ui port "):
            raw_port = text[len(":ui port ") :].strip()
            try:
                port = int(raw_port)
            except ValueError:
                port = 0
            if not 1 <= port <= 65535:
                print("usage: :ui port 1..65535")
                continue
            current = ui_state.get("ui")
            if isinstance(current, WebUI) and current.active:
                print("stop the web ui before changing the port")
                continue
            config.web.port = port
            persist()
            print(f"web ui port set to {port}")
            continue
        if text == ":clear":
            conversation.clear()
            print("context cleared")
            continue
        if text == ":good" or text.startswith(":good "):
            record_feedback(1, text[len(":good") :].strip())
            continue
        if text == ":bad" or text.startswith(":bad "):
            record_feedback(-1, text[len(":bad") :].strip())
            continue
        if text == ":feedback clear":
            if storage is None:
                print("feedback needs the database; start AKKI without --no-db")
            else:
                removed = storage.clear_feedback()
                print(f"cleared {removed} feedback entries")
            continue
        if text == ":feedback":
            show_feedback()
            continue
        if text == ":voice":
            ready = "yes" if piper_ready(config.voice.piper_voice) else "no"
            speakers = piper_num_speakers(config.voice.piper_voice)
            piper_speaker = config.voice.piper_speaker
            speaker_state = (
                "default" if piper_speaker is None else str(piper_speaker)
            )
            print(
                f"auto_speak={'on' if config.voice.auto_speak else 'off'} "
                f"engine={config.voice.tts_engine} "
                f"edge_voice={config.voice.edge_voice} "
                f"nsfw_edge_voice={config.voice.nsfw_edge_voice} "
                f"hindi_edge_voice={config.voice.hindi_edge_voice} "
                f"nsfw_hindi_edge_voice={config.voice.nsfw_hindi_edge_voice} "
                f"piper_voice={config.voice.piper_voice} installed={ready} "
                f"speaker={speaker_state}/{speakers} "
                f"sapi_voice={config.voice.voice_name or 'default'} "
                f"rate={config.voice.rate} "
                f"pitch={config.voice.tts_pitch} "
                f"stt_model={config.voice.stt_model} "
                f"stt_language={config.voice.stt_language} "
                f"hotkey={config.voice.hotkey} "
                f"hotkey_autostart={'on' if config.voice.hotkey_enabled else 'off'} "
                f"wake={config.voice.wake_word} "
                f"wake_autostart={'on' if config.voice.wake_enabled else 'off'}"
            )
            continue
        if text in {":voice on", ":voice off"}:
            config.voice.auto_speak = text.endswith("on")
            persist()
            print(f"auto-speak {'on' if config.voice.auto_speak else 'off'}")
            continue
        if text.startswith(":voice use "):
            engine = text[len(":voice use ") :].strip().lower()
            if engine not in {"piper", "sapi", "edge"}:
                print("usage: :voice use piper|sapi|edge")
            else:
                config.voice.tts_engine = engine
                persist()
                print(f"tts engine set to {engine}")
            continue
        if text in {":voice indian", ":voice indian-male"}:
            config.voice.tts_engine = "edge"
            config.voice.edge_voice = "en-IN-PrabhatNeural"
            config.voice.auto_speak = True
            persist()
            print("voice set to Indian English (Edge neural, male)")
            continue
        if text == ":voice indian-female":
            config.voice.tts_engine = "edge"
            config.voice.edge_voice = "en-IN-NeerjaNeural"
            config.voice.auto_speak = True
            persist()
            print("voice set to Indian English (Edge neural, female)")
            continue
        if text == ":voice hindi":
            config.voice.tts_engine = "edge"
            config.voice.hindi_edge_voice = "hi-IN-MadhurNeural"
            config.voice.auto_speak = True
            persist()
            print("Hindi voice set to hi-IN-MadhurNeural (Edge neural, male)")
            continue
        if text == ":voice hindi-female":
            config.voice.tts_engine = "edge"
            config.voice.hindi_edge_voice = "hi-IN-SwaraNeural"
            config.voice.auto_speak = True
            persist()
            print("Hindi voice set to hi-IN-SwaraNeural (Edge neural, female)")
            continue
        if text.startswith(":voice edge "):
            edge_voice = text[len(":voice edge ") :].strip()
            if not edge_voice:
                print("usage: :voice edge <voice-id>")
                continue
            config.voice.tts_engine = "edge"
            config.voice.edge_voice = edge_voice
            persist()
            print(f"edge voice set to {edge_voice}")
            continue
        if text == ":voice batman":
            config.voice.tts_engine = "piper"
            config.voice.piper_voice = "en_US-ryan-high"
            config.voice.piper_length_scale = 0.7
            config.voice.tts_pitch = -12
            config.voice.auto_speak = True
            persist()
            print("voice set to Batman (Piper neural, deep)")
            continue
        if text.startswith(":voice pitch "):
            raw = text[len(":voice pitch ") :].strip()
            try:
                pitch = int(raw)
            except ValueError:
                pitch = 101
            if pitch < -50 or pitch > 50:
                print("usage: :voice pitch -50..50")
                continue
            config.voice.tts_pitch = pitch
            persist()
            print(f"voice pitch set to {pitch}%")
            continue
        if text == ":voice options":
            current = resolve_voice_id(config.voice.piper_voice)
            for voice_id, description in piper_catalog():
                marker = "*" if voice_id == current else " "
                state = "installed" if piper_ready(voice_id) else ""
                print(f" {marker} {voice_id:<40} {description} {state}")
            print(
                " aliases: hindi, hindi-female, bhojpuri, bhojpuri-female, "
                "marathi, malayalam, telugu, urdu"
            )
            print(
                " edge voices: en-IN-PrabhatNeural (male), "
                "en-IN-NeerjaNeural (female), "
                "en-IN-NeerjaExpressiveNeural (nsfw female), "
                "hi-IN-MadhurNeural (hindi male), "
                "hi-IN-SwaraNeural (hindi female)"
            )
            continue
        if text.startswith(":voice set "):
            voice_id = text[len(":voice set ") :].strip()
            if not voice_id:
                print("usage: :voice set <voice-id>")
                continue
            voice_id = resolve_voice_id(voice_id)
            try:
                piper_voice_urls(voice_id)
            except VoiceError as exc:
                print(f"voice: {exc}")
                continue
            print(f"installing {voice_id}...")
            try:
                ensure_piper(voice_id)
            except (VoiceError, OSError) as exc:
                print(f"voice: {exc}")
                continue
            config.voice.piper_voice = voice_id
            config.voice.tts_engine = "piper"
            speakers = piper_num_speakers(voice_id)
            if speakers > 1:
                if (
                    config.voice.piper_speaker is None
                    or config.voice.piper_speaker >= speakers
                ):
                    config.voice.piper_speaker = 0
            else:
                config.voice.piper_speaker = None
            persist()
            print(f"voice set to {voice_id}")
            if speakers > 1:
                print(
                    f"this voice has {speakers} speakers; "
                    f"using {config.voice.piper_speaker} (change with :voice speaker N)"
                )
            continue
        if text.startswith(":voice speaker "):
            value = text[len(":voice speaker ") :].strip().lower()
            speakers = piper_num_speakers(config.voice.piper_voice)
            if value in {"auto", "default", "none"}:
                config.voice.piper_speaker = None
                persist()
                print(f"speaker set to default (voice has {speakers})")
                continue
            try:
                speaker_number = int(value)
            except ValueError:
                speaker_number = -1
            if speaker_number < 0 or speaker_number >= speakers:
                print(
                    f"usage: :voice speaker 0..{speakers - 1} (or auto); "
                    f"current voice {config.voice.piper_voice} has {speakers}"
                )
                continue
            config.voice.piper_speaker = speaker_number
            persist()
            print(f"speaker set to {speaker_number}")
            continue
        if text == ":voice setup":
            state = {"last": -1}

            def progress(done: int, total: int, label: str) -> None:
                percent = int(done * 100 / total) if total else 0
                if percent != state["last"]:
                    print(f"  {label}: {percent}%", end="\r", flush=True)
                    state["last"] = percent

            try:
                ensure_piper(config.voice.piper_voice, progress)
            except (VoiceError, OSError) as exc:
                print(f"\nvoice: {exc}")
            else:
                print(" " * 60, end="\r")
                print(f"piper ready: {config.voice.piper_voice}")
            continue
        if text == ":voice list":
            try:
                voices = list_voices()
            except VoiceError as exc:
                print(f"voice: {exc}")
            else:
                for name in voices:
                    print(f"  {name}")
            continue
        if text.startswith(":say "):
            spoken = text[len(":say ") :].strip()
            if not spoken:
                print("usage: :say <text>")
            else:
                try:
                    speak_text(spoken, config)
                except VoiceError as exc:
                    print(f"voice: {exc}")
            continue
        if text == ":message" or text == ":dictate":
            indicator.show()
            try:
                transcript = listen(
                    config.voice.stt_model, config.voice.stt_language
                )
            except VoiceError as exc:
                print(f"voice: {exc}")
                continue
            finally:
                indicator.hide()
            if not transcript.strip():
                print("no speech detected")
                continue
            print(f"you said: {transcript}")
            print(describe(compose_message(transcript)))
            continue
        if text.startswith(":message ") or text.startswith(":dictate "):
            message_text = text.split(" ", 1)[1].strip()
            if not message_text:
                print("usage: :message <text>")
                continue
            print(describe(compose_message(message_text)))
            continue
        if text == ":listen":
            indicator.show()
            try:
                transcript = listen(
                    config.voice.stt_model, config.voice.stt_language
                )
            except VoiceError as exc:
                print(f"voice: {exc}")
                continue
            finally:
                indicator.hide()
            print(f"you said: {transcript}")
            if is_farewell(transcript):
                say_goodbye()
                continue
            respond_visible(transcript)
            start_conversation()
            continue
        if text.startswith(":remember "):
            fact = text[len(":remember ") :].strip()
            if storage is None:
                print("database unavailable")
            else:
                try:
                    memory_id = storage.remember(fact)
                    print(f"remembered #{memory_id}: {fact}")
                except ValueError as exc:
                    print(f"failed: {exc}")
            continue
        if text == ":memories":
            if storage is None:
                print("database unavailable")
            else:
                entries = storage.memories()
                if not entries:
                    print("no memories")
                for memory_id, fact in entries:
                    print(f"  #{memory_id}  {fact}")
            continue
        if text.startswith(":forget "):
            raw_id = text[len(":forget ") :].strip()
            if storage is None:
                print("database unavailable")
            else:
                try:
                    memory_id = int(raw_id)
                except ValueError:
                    print("usage: :forget <id>")
                else:
                    removed = storage.forget(memory_id)
                    print("forgotten" if removed else f"no memory #{memory_id}")
            continue
        if text == ":cache clear":
            if storage is None:
                print("database unavailable")
            else:
                print(f"removed {storage.purge_cache(expired_only=False)} entries")
            continue
        if text == ":cache":
            if storage is None:
                print("database unavailable")
            else:
                stats = storage.cache_stats()
                print(f"entries={stats['entries']} expired={stats['expired']}")
            continue
        if text == ":db":
            print(config.db_path)
            continue
        if text == ":llm":
            base, model, key_env = resolve_endpoint(config.llm)
            key_state = "set" if os.environ.get(key_env) else "missing"
            print(
                f"cloud provider={config.llm.provider} model={model} "
                f"enabled={config.llm.enabled}")
            print(f"cloud base={base} key={key_env} ({key_state})")
            print(
                f"local model={config.llm.local_model} "
                f"enabled={config.llm.local_enabled} "
                f"first={config.llm.local_first} "
                f"base={config.llm.local_base_url}")
            continue
        if via_voice and is_farewell(text):
            say_goodbye()
            continue
        respond_visible(text)
        if via_voice:
            start_conversation()


def _configure_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if os.name == "nt" and sys.stdout.isatty():
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except (AttributeError, OSError):
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()

    parser = argparse.ArgumentParser(prog="akki", description="AKKI local assistant")
    parser.add_argument("command", nargs="*", help="one-shot command to execute")
    parser.add_argument("--config", type=Path, default=None, help="config file path")
    parser.add_argument("--tools", action="store_true", help="list registered tools")
    parser.add_argument("--speak", action="store_true", help="speak the one-shot reply")
    parser.add_argument("--no-db", action="store_true", help="disable storage and cache")
    parser.add_argument("--ui", action="store_true", help="start the local web UI with the REPL")
    parser.add_argument("--tray", action="store_true", help="start the tray icon with the REPL")
    parser.add_argument("--panel", action="store_true", help="open the settings panel with the REPL")
    parser.add_argument("--widget", action="store_true", help="open the desktop access widget with the REPL")
    parser.add_argument("--widget-only", action="store_true", help="run only the desktop access widget")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run hotkey and wake listeners without the console",
    )
    args = parser.parse_args(argv)

    try:
        logfile = configure_logging()
    except OSError as exc:
        print(f"warning: logging unavailable: {exc}", file=sys.stderr)
    else:
        logger.info(
            "start version=%s mode=%s log=%s",
            __version__,
            "once" if args.command else "repl",
            logfile,
        )

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("config load failed")
        print(f"failed to load config: {exc}", file=sys.stderr)
        return 1

    secrets_store = SecretsStore()
    try:
        secrets_store.load_into_env()
    except (SecretError, OSError) as exc:
        print(f"warning: stored secrets unavailable: {exc}", file=sys.stderr)

    storage: Storage | None = None
    if not args.no_db:
        try:
            storage = Storage(config.db_path)
        except (sqlite3.Error, OSError) as exc:
            print(f"warning: database unavailable: {exc}", file=sys.stderr)

    registry = build_registry(config, storage)

    if args.tools:
        for spec in registry.specs():
            print(f"{spec.name:<12} {spec.level.value:<10} {spec.description}")
        return 0

    if config.voice.tts_engine == "piper" and config.voice.auto_speak:
        threading.Thread(
            target=prewarm_piper,
            args=(
                config.voice.piper_voice,
                config.voice.piper_length_scale,
                config.voice.piper_speaker,
            ),
            name="akki-tts-prewarm",
            daemon=True,
        ).start()

    try:
        if args.command:
            return run_once(
                " ".join(args.command),
                config,
                registry,
                storage,
                speak_reply=args.speak,
            )
        return repl(
            config,
            registry,
            storage,
            args.config or config_path(),
            start_ui=args.ui,
            start_tray=args.tray,
            start_panel=args.panel,
            start_widget=args.widget,
            widget_only=args.widget_only,
            headless=args.headless,
            secrets_store=secrets_store,
        )
    finally:
        if storage is not None:
            storage.close()
        logger.info("stop")


if __name__ == "__main__":
    raise SystemExit(main())
