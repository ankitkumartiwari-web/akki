from __future__ import annotations

import argparse
import logging
import os
import queue
import sqlite3
import sys
import threading
import time
from functools import partial
from pathlib import Path

from . import __version__
from .config import Config, config_path, load_config, save_config
from .conversation import Conversation, resolve_followup
from .hotkey import HotkeyError, HotkeyListener, hotkey_supported
from .llm import ask_cloud, ask_local, build_system_prompt, resolve_endpoint
from .logsetup import configure_logging, log_path
from .models import ActionLevel, ToolResult
from .permissions import ask_confirmation
from .registry import ToolRegistry
from .router import route
from .storage import Storage, make_cache_key
from .voice import (
    VoiceError,
    ensure_piper,
    list_voices,
    listen,
    listen_push,
    piper_catalog,
    piper_num_speakers,
    piper_ready,
    piper_voice_urls,
    resolve_voice_id,
    speak,
)

logger = logging.getLogger("odin.cli")
from .tools import (
    change_volume,
    find_files,
    launch_app,
    open_in_app,
    open_path,
    open_url,
    take_screenshot,
    web_search,
)

BANNER = "ODIN {version} - local-first assistant. Type :help for commands."


def build_registry(config: Config) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "launch_app",
        "Launch a configured application",
        ActionLevel.REVERSIBLE,
        partial(launch_app, config=config),
        {"alias": "application name or alias"},
    )
    registry.register(
        "open_in_app",
        "Open a file or folder in a configured application",
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
        return f"ODIN: {result.message}{suffix}"
    status = "OK" if result.ok else "FAILED"
    proof = "verified" if result.verified else "unverified"
    suffix = " [cached]" if result.data.get("cached") else ""
    lines = [f"{status} ({proof}){suffix}: {result.message}"]
    matches = result.data.get("matches")
    if matches:
        lines.extend(f"  {entry}" for entry in matches)
    return "\n".join(lines)


def handle(
    text: str,
    config: Config,
    registry: ToolRegistry,
    conversation: Conversation | None = None,
    storage: Storage | None = None,
) -> ToolResult:
    conversation = conversation if conversation is not None else Conversation()
    request = route(text, config)
    if request is None:
        request = resolve_followup(text, conversation)

    if request is not None:
        logger.info("route action tool=%s", request.tool)
        result = registry.execute(
            request,
            profile=config.profile,
            confirm=lambda prompt: ask_confirmation(prompt),
        )
        if result.ok:
            conversation.record(request, result)
    else:
        memory = [fact for _, fact in storage.memories()] if storage else None
        learned = storage.recent_feedback(6) if storage else None
        history = conversation.cloud_messages()
        system = build_system_prompt(memory, config.profile, learned)
        errors: list[str] = []

        def run_tier(
            provider: str,
            model: str,
            call: object,
        ) -> ToolResult | None:
            cache_key = None
            if storage is not None and config.llm.cache_ttl_seconds > 0:
                cache_key = make_cache_key(provider, model, system, history, text)
                hit = storage.cache_get(cache_key)
                if hit is not None:
                    return ToolResult.success(
                        hit, data={"reply": True, "cached": True}
                    )
            outcome = call()
            if outcome.request is not None:
                executed = registry.execute(
                    outcome.request,
                    profile=config.profile,
                    confirm=lambda prompt: ask_confirmation(prompt),
                )
                if executed.ok:
                    conversation.record(outcome.request, executed)
                return executed
            if outcome.text:
                if storage is not None and cache_key is not None:
                    storage.cache_put(
                        cache_key, outcome.text, config.llm.cache_ttl_seconds
                    )
                return ToolResult.success(outcome.text, data={"reply": True})
            if outcome.error:
                errors.append(outcome.error)
            return None

        _, cloud_model, _ = resolve_endpoint(config.llm)
        tiers: list[tuple[str, str, object]] = []
        if config.llm.local_enabled:
            tiers.append(
                (
                    "ollama",
                    config.llm.local_model,
                    lambda: ask_local(
                        text,
                        registry,
                        config.llm,
                        history=history,
                        memory=memory,
                        profile=config.profile,
                        feedback=learned,
                    ),
                )
            )
        if config.llm.enabled:
            tiers.append(
                (
                    config.llm.provider,
                    cloud_model,
                    lambda: ask_cloud(
                        text,
                        registry,
                        config.llm,
                        history=history,
                        memory=memory,
                        profile=config.profile,
                        feedback=learned,
                    ),
                )
            )
        if not config.llm.local_first:
            tiers.reverse()

        result = None
        for provider, model, call in tiers:
            result = run_tier(provider, model, call)
            if result is not None:
                break
        if result is None:
            result = ToolResult.failure(
                " | ".join(errors) or "no local or cloud model is available"
            )

    logger.info("reply ok=%s verified=%s", result.ok, result.verified)
    conversation.add("user", text)
    conversation.add("assistant", result.message)
    return result


def speak_text(text: str, config: Config) -> None:
    speak(
        text,
        rate=config.voice.rate,
        volume=config.voice.volume,
        voice_name=config.voice.voice_name,
        engine=config.voice.tts_engine,
        piper_voice=config.voice.piper_voice,
        piper_length_scale=config.voice.piper_length_scale,
        piper_speaker=config.voice.piper_speaker,
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
    print("  open <app>                 launch a configured application")
    print("  open <site or URL>         open a website (e.g. open youtube)")
    print("  open <file or folder>      open with the default handler")
    print("  open <project> in <app>    open a file or folder in an app")
    print("  search <terms>             web search")
    print("  find <name>                search configured folders")
    print("  take a screenshot          save a screen capture")
    print("  increase/decrease volume   change volume")
    print("  :tools                     list registered tools")
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
    print("  :hotkey                    show the push-to-talk hotkey state")
    print("  :hotkey on|off             enable Ctrl+Space push-to-talk")
    print("  :stt                       show speech-to-text settings")
    print("  :stt model <name>          switch whisper model, e.g. small")
    print("  :stt language <code|auto>  force recognition language")
    print("  :logs                      show the audit log path")
    print("  :say <text>                speak text aloud")
    print("  :voice                     show voice settings")
    print("  :voice on|off              toggle spoken replies")
    print("  :voice setup               install the Piper neural voice")
    print("  :voice set <voice-id>      switch Piper voice (downloads if needed)")
    print("  :voice options             list available Piper voices")
    print("  :voice speaker N|auto      pick a speaker for multi-speaker voices")
    print("  :voice use piper|sapi      choose the tts engine")
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

    def stop_capture() -> None:
        stop = hotkey_state.get("stop")
        if isinstance(stop, threading.Event):
            stop.set()

    def capture_voice() -> None:
        stop_event = threading.Event()
        hotkey_state["stop"] = stop_event
        print(
            "\r[mic] listening... press Ctrl+Space again to stop",
            flush=True,
        )
        try:
            transcript = listen_push(
                config.voice.stt_model,
                config.voice.stt_language,
                stop_event=stop_event,
            )
        except VoiceError as exc:
            print(f"\r[mic] {exc}", flush=True)
            pending.put("")
        except Exception as exc:
            logger.exception("hotkey capture failed")
            print(f"\r[mic] capture failed: {exc}", flush=True)
            pending.put("")
        else:
            pending.put(transcript)
        finally:
            hotkey_state["stop"] = None

    def on_hotkey() -> None:
        worker = hotkey_state.get("capture")
        if isinstance(worker, threading.Thread) and worker.is_alive():
            stop_capture()
            return
        worker = threading.Thread(
            target=capture_voice, name="odin-capture", daemon=True
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
            print("feedback needs the database; start ODIN without --no-db")
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
    while True:
        try:
            raw, via_voice = read_line("odin> ")
            text = raw.strip()
        except (EOFError, KeyboardInterrupt):
            print()
            stop_hotkey()
            return 0
        if via_voice and text:
            print(f"[mic] heard: {text}")
        if not text:
            continue
        if text in {":quit", ":exit", ":q"}:
            stop_hotkey()
            return 0
        if text == ":help":
            print_help()
            continue
        if text == ":tools":
            for spec in registry.specs():
                print(f"  {spec.name:<12} {spec.level.value:<10} {spec.description}")
            continue
        if text == ":config":
            print(config_path())
            continue
        if text == ":logs":
            print(log_path())
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
                print("feedback needs the database; start ODIN without --no-db")
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
            speaker = config.voice.piper_speaker
            speaker_state = "default" if speaker is None else str(speaker)
            print(
                f"auto_speak={'on' if config.voice.auto_speak else 'off'} "
                f"engine={config.voice.tts_engine} "
                f"piper_voice={config.voice.piper_voice} installed={ready} "
                f"speaker={speaker_state}/{speakers} "
                f"sapi_voice={config.voice.voice_name or 'default'} "
                f"rate={config.voice.rate} "
                f"stt_model={config.voice.stt_model} "
                f"stt_language={config.voice.stt_language} "
                f"hotkey={config.voice.hotkey} "
                f"hotkey_autostart={'on' if config.voice.hotkey_enabled else 'off'}"
            )
            continue
        if text in {":voice on", ":voice off"}:
            config.voice.auto_speak = text.endswith("on")
            persist()
            print(f"auto-speak {'on' if config.voice.auto_speak else 'off'}")
            continue
        if text.startswith(":voice use "):
            engine = text[len(":voice use ") :].strip().lower()
            if engine not in {"piper", "sapi"}:
                print("usage: :voice use piper|sapi")
            else:
                config.voice.tts_engine = engine
                persist()
                print(f"tts engine set to {engine}")
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
                speaker = int(value)
            except ValueError:
                speaker = -1
            if speaker < 0 or speaker >= speakers:
                print(
                    f"usage: :voice speaker 0..{speakers - 1} (or auto); "
                    f"current voice {config.voice.piper_voice} has {speakers}"
                )
                continue
            config.voice.piper_speaker = speaker
            persist()
            print(f"speaker set to {speaker}")
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
        if text == ":listen":
            try:
                transcript = listen(
                    config.voice.stt_model, config.voice.stt_language
                )
            except VoiceError as exc:
                print(f"voice: {exc}")
                continue
            print(f"you said: {transcript}")
            respond(transcript, config, registry, conversation, storage)
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
        respond(text, config, registry, conversation, storage)


def _configure_stdio() -> None:
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

    parser = argparse.ArgumentParser(prog="odin", description="ODIN local assistant")
    parser.add_argument("command", nargs="*", help="one-shot command to execute")
    parser.add_argument("--config", type=Path, default=None, help="config file path")
    parser.add_argument("--tools", action="store_true", help="list registered tools")
    parser.add_argument("--speak", action="store_true", help="speak the one-shot reply")
    parser.add_argument("--no-db", action="store_true", help="disable storage and cache")
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

    registry = build_registry(config)

    if args.tools:
        for spec in registry.specs():
            print(f"{spec.name:<12} {spec.level.value:<10} {spec.description}")
        return 0

    storage: Storage | None = None
    if not args.no_db:
        try:
            storage = Storage(config.db_path)
        except (sqlite3.Error, OSError) as exc:
            print(f"warning: database unavailable: {exc}", file=sys.stderr)

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
        )
    finally:
        if storage is not None:
            storage.close()
        logger.info("stop")


if __name__ == "__main__":
    raise SystemExit(main())
