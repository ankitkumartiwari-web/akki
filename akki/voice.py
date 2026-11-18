from __future__ import annotations

import base64
import importlib.util
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
import zipfile
from pathlib import Path
from typing import Any, Callable

from .config import database_path

logger = logging.getLogger("akki.voice")

PIPER_RELEASE_URL = (
    "https://github.com/rhasspy/piper/releases/download/"
    "2023.11.14-2/piper_windows_amd64.zip"
)
PIPER_VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"
STT_INITIAL_PROMPT = (
    "Hey Akki, hi, hello, good morning, thank you, akki change, open Chrome, "
    "open YouTube, volume up, volume down, mute, take a screenshot, what is the "
    "time, what is the date, play music, pause, search the web, Hindi, Hinglish, "
    "India."
)
STT_HALLUCINATIONS = (
    "the content of this video is very good",
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "subtitles by",
    "amara.org",
)

_PIPER_VOICE_CACHE: dict[tuple[str, str], Any] = {}
_PIPER_LOCK = threading.RLock()

PIPER_CATALOG = {
    "en_US-lessac-medium": "US English, neutral and clear",
    "en_US-amy-medium": "US English, female",
    "en_US-kristin-medium": "US English, female, softer",
    "en_US-ryan-high": "US English, male, high quality",
    "en_US-joe-medium": "US English, male",
    "en_GB-alba-medium": "British English, Scottish female",
    "en_GB-northern_english_male-medium": "British English, northern male",
    "hi_IN-pratham-medium": "Hindi, male",
    "hi_IN-priyamvada-medium": "Hindi, female",
    "hi_IN-rohan-medium": "Hindi, male, expressive",
    "mr_IN-google-medium": "Marathi, 9 speakers (see :voice speaker)",
    "ml_IN-arjun-medium": "Malayalam, male",
    "ml_IN-meera-medium": "Malayalam, female",
    "te_IN-maya-medium": "Telugu, female",
    "te_IN-padmavathi-medium": "Telugu, female, formal",
    "te_IN-venkatesh-medium": "Telugu, male",
    "ur_PK-fasih-medium": "Urdu, male",
    "ur_PK-aegis_female-medium": "Urdu, female",
}

VOICE_ALIASES = {
    "hindi": "hi_IN-pratham-medium",
    "hindi-male": "hi_IN-pratham-medium",
    "hindi-female": "hi_IN-priyamvada-medium",
    "bhojpuri": "hi_IN-pratham-medium",
    "bhojpuri-female": "hi_IN-priyamvada-medium",
    "marathi": "mr_IN-google-medium",
    "malayalam": "ml_IN-arjun-medium",
    "telugu": "te_IN-maya-medium",
    "urdu": "ur_PK-fasih-medium",
}


def resolve_voice_id(value: str) -> str:
    cleaned = value.strip()
    return VOICE_ALIASES.get(cleaned.lower(), cleaned)

_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\uFE0F\u200D\u20E3"
    "]+"
)

Progress = Callable[[int, int, str], None]

_DEVANAGARI_NAME = re.compile(r"आक्की|आकी|अक्कि|अक्की|अकी")
_LATIN_NAME = re.compile(r"(?i)\b(?:a{1,2}k{1,2}i+)\b")


def normalize_name_pronunciation(text: str, voice: str) -> str:
    if voice.strip().lower().startswith("hi-"):
        text = _LATIN_NAME.sub("अक्की", text)
        return _DEVANAGARI_NAME.sub("अक्की", text)
    return _DEVANAGARI_NAME.sub("Akki", text)


def clean_for_speech(text: str) -> str:
    value = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[-*+]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\d+[.)]\s+", "", value, flags=re.MULTILINE)
    value = value.replace("**", "").replace("__", "").replace("~~", "")
    value = re.sub(r"[*#~`]", "", value)
    value = _EMOJI.sub("", value)
    value = re.sub(r":[a-zA-Z0-9_+\-]+:", "", value)
    value = value.replace("â€”", ", ").replace("â€“", ", ")
    value = value.replace("…", ", ").replace("•", " ").replace("·", " ")
    value = re.sub(r"\.{2,}", ", ", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"[,;:]{2,}", ",", value)
    value = " ".join(value.split()).strip()
    return value.strip(" -")


def piper_catalog() -> list[tuple[str, str]]:
    return list(PIPER_CATALOG.items())


class VoiceError(RuntimeError):
    pass


class VoicePlaybackError(VoiceError):
    pass


NO_WINDOW_FLAGS = (
    {"creationflags": 0x08000000} if os.name == "nt" else {}
)


def _model_dir() -> Path:
    path = database_path().parent / "models" / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _powershell(script: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            **NO_WINDOW_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoiceError(f"powershell failed: {exc}") from exc


def speech_script(
    text: str,
    rate: int = 1,
    volume: int = 100,
    voice_name: str = "",
    pitch: int = 0,
) -> str:
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    lines = [
        "Add-Type -AssemblyName System.Speech",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
        f"$s.Rate = {max(-10, min(10, int(rate)))}",
        f"$s.Volume = {max(0, min(100, int(volume)))}",
    ]
    if voice_name:
        safe = voice_name.replace("'", "''")
        lines.append(f"try {{ $s.SelectVoice('{safe}') }} catch {{}}")
    lines.append(
        "$text = [Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{payload}'))"
    )
    if pitch:
        amount = max(-50, min(50, int(pitch)))
        lines.extend(
            [
                "$escaped = [System.Security.SecurityElement]::Escape($text)",
                (
                    "$ssml = \"<speak version='1.0' "
                    "xmlns='http://www.w3.org/2001/10/synthesis' "
                    f"xml:lang='en-US'><prosody pitch='{amount}%'>"
                    "$escaped</prosody></speak>\""
                ),
                "$s.SpeakSsml($ssml)",
            ]
        )
    else:
        lines.append("$s.Speak($text)")
    return "\n".join(lines)


def _speak_sapi(
    text: str,
    rate: int = 1,
    volume: int = 100,
    voice_name: str = "",
    timeout: float = 120.0,
    pitch: int = 0,
) -> None:
    if os.name != "nt":
        raise VoiceError("text-to-speech uses Windows SAPI and is only available on Windows")
    result = _powershell(
        speech_script(text, rate, volume, voice_name, pitch), timeout=timeout
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise VoiceError(f"speech synthesis failed: {detail or result.returncode}")


def _play_audio_file(path: Path, timeout: float) -> None:
    exe = shutil.which("ffplay")
    if exe is None:
        raise VoiceError("edge tts playback needs ffplay; install ffmpeg")
    try:
        result = subprocess.run(
            [
                exe,
                "-nodisp",
                "-autoexit",
                "-hide_banner",
                "-loglevel",
                "quiet",
                str(path),
            ],
            timeout=timeout,
            capture_output=True,
            **NO_WINDOW_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoicePlaybackError(f"could not play audio: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        raise VoicePlaybackError(
            f"could not play audio: {detail.strip() or result.returncode}"
        )


def speak_edge(
    text: str,
    voice: str = "en-IN-PrabhatNeural",
    rate: int = 1,
    volume: int = 100,
    pitch: int = 0,
    timeout: float = 120.0,
) -> None:
    text = clean_for_speech(text)
    if not text:
        return
    text = normalize_name_pronunciation(text, voice)
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError(
            "edge tts needs the edge-tts package: pip install edge-tts"
        ) from exc
    import asyncio

    handle = tempfile.NamedTemporaryFile(
        suffix=".mp3", prefix="akki-edge-", delete=False
    )
    handle.close()
    output = Path(handle.name)
    try:
        communicate = edge_tts.Communicate(
            text,
            voice=voice,
            rate=f"{int(rate) * 5:+d}%",
            volume=f"{int(volume) - 100:+d}%",
            pitch=f"{int(pitch) * 2:+d}Hz",
        )
        asyncio.run(communicate.save(str(output)))
        if not output.is_file() or output.stat().st_size == 0:
            raise VoiceError("edge tts produced no audio")
        _play_audio_file(output, timeout)
    except VoiceError:
        raise
    except Exception as exc:
        raise VoiceError(f"edge tts failed: {exc}") from exc
    finally:
        output.unlink(missing_ok=True)


def speak(
    text: str,
    rate: int = 1,
    volume: int = 100,
    voice_name: str = "",
    engine: str = "sapi",
    piper_voice: str = DEFAULT_PIPER_VOICE,
    piper_length_scale: float = 1.0,
    timeout: float = 120.0,
    piper_speaker: int | None = None,
    pitch: int = 0,
    edge_voice: str = "en-IN-PrabhatNeural",
) -> None:
    cleaned = clean_for_speech(text)
    if not cleaned:
        return
    engine = engine.strip().lower()
    if engine == "piper":
        speak_piper(
            cleaned,
            piper_voice,
            piper_length_scale,
            timeout,
            piper_speaker,
            pitch,
        )
        return
    if engine == "edge":
        try:
            speak_edge(cleaned, edge_voice, rate, volume, pitch, timeout)
        except VoicePlaybackError as exc:
            logger.warning("edge tts playback failed: %s", exc)
            raise
        except VoiceError as exc:
            logger.warning("edge tts failed, falling back to piper: %s", exc)
            speak_piper(
                cleaned,
                piper_voice,
                piper_length_scale,
                timeout,
                piper_speaker,
                pitch,
            )
        return
    if engine == "sapi":
        _speak_sapi(cleaned, rate, volume, voice_name, timeout, pitch)
        return
    raise VoiceError(f"unknown tts engine: {engine} (use piper, sapi or edge)")


def list_voices() -> list[str]:
    if os.name != "nt":
        raise VoiceError("voice listing is only available on Windows")
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
    )
    result = _powershell(script, timeout=30.0)
    if result.returncode != 0:
        raise VoiceError((result.stderr or "could not list voices").strip())
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _resolve_input_device(sd: Any) -> int | str | None:
    override = os.environ.get("AKKI_MIC_DEVICE")
    if override:
        try:
            return int(override)
        except ValueError:
            return override
    default = sd.default.device
    default_input = default[0] if hasattr(default, "__getitem__") else default
    devices = list(sd.query_devices())

    def can_input(index: int) -> bool:
        try:
            info = sd.query_devices(index, "input")
            return int(info["max_input_channels"]) > 0
        except Exception:
            return False

    if isinstance(default_input, int) and default_input >= 0 and can_input(default_input):
        return default_input

    candidates = [
        (index, device)
        for index, device in enumerate(devices)
        if int(device.get("max_input_channels", 0)) > 0
    ]

    def score(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, device = item
        name = str(device.get("name", "")).lower()
        if "stereo mix" in name or "pc speaker" in name:
            return (9, index)
        if "microphone array" in name:
            if int(device.get("default_samplerate", 0)) == 16000:
                return (0, index)
            return (1, index)
        if "microphone" in name:
            return (2, index)
        if "realtek" in name:
            return (3, index)
        if "headset" in name:
            return (5, index)
        return (4, index)

    if candidates:
        candidates.sort(key=score)
        return candidates[0][0]
    return None


def _choose_samplerate(sd: Any, device: int | str | None, preferred: int) -> int:
    seen: set[int] = set()
    for rate in (preferred, 48000, 44100, 32000, 22050, 16000):
        if rate in seen:
            continue
        seen.add(rate)
        try:
            sd.check_input_settings(
                device=device,
                samplerate=rate,
                channels=1,
                dtype="int16",
            )
            return rate
        except Exception:
            continue
    if isinstance(device, int):
        try:
            return int(sd.query_devices(device)["default_samplerate"])
        except Exception:
            pass
    return preferred


def record_to_wav(path: Path, samplerate: int = 16000) -> Path:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceError(
            "recording needs sounddevice: pip install sounddevice"
        ) from exc

    device = _resolve_input_device(sd)
    if device is None:
        raise VoiceError("no microphone input device was found")
    samplerate = _choose_samplerate(sd, device, samplerate)

    frames: list[bytes] = []

    def callback(indata: bytes, frame_count: int, time_info: object, status: object) -> None:
        frames.append(bytes(indata))

    try:
        stream = sd.RawInputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            device=device,
            callback=callback,
        )
    except Exception as exc:
        raise VoiceError(f"could not open the microphone: {exc}") from exc

    print("listening... press Enter to stop")
    with stream:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass

    data = b"".join(frames)
    if not data:
        raise VoiceError("no audio was captured")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(samplerate)
        handle.writeframes(data)
    return path


_models: dict[str, object] = {}


def _whisper_model(model_size: str) -> object:
    cached = _models.get(model_size)
    if cached is not None:
        return cached
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise VoiceError(
            "speech-to-text needs faster-whisper: pip install faster-whisper"
        ) from exc
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        download_root=str(_model_dir()),
    )
    _models[model_size] = model
    return model


def transcribe(
    path: Path | str,
    model_size: str = "small",
    language: str = "auto",
) -> str:
    detected: str | None = None
    if model_size.endswith(".en"):
        detected = "en"
    elif language and language.lower() != "auto":
        detected = language
    if detected == "en" and model_size in {"tiny", "base", "small", "medium"}:
        model_size = model_size + ".en"
    model = _whisper_model(model_size)
    segments, _ = model.transcribe(
        str(path),
        language=detected,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=STT_INITIAL_PROMPT,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text or _is_stt_hallucination(text):
        raise VoiceError("could not transcribe any speech")
    return text


def _is_stt_hallucination(text: str) -> bool:
    normalized = " ".join(text.lower().replace("’", "'").split()).strip(" .!?,")
    return any(
        normalized == phrase or normalized.startswith(phrase + " ")
        for phrase in STT_HALLUCINATIONS
    )


def listen(model_size: str = "small", language: str = "auto") -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="akki-", delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        record_to_wav(path)
        return transcribe(path, model_size, language)
    finally:
        path.unlink(missing_ok=True)


def record_until_silence(
    path: Path,
    samplerate: int = 16000,
    *,
    stop_event: threading.Event | None = None,
    max_seconds: float = 20.0,
    silence_seconds: float = 1.2,
    threshold: int | None = None,
) -> tuple[Path, bool]:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceError(
            "recording needs sounddevice: pip install sounddevice"
        ) from exc

    device = _resolve_input_device(sd)
    if device is None:
        raise VoiceError("no microphone input device was found")
    samplerate = _choose_samplerate(sd, device, samplerate)

    limit = threshold
    if limit is None:
        limit = int(os.environ.get("AKKI_MIC_THRESHOLD", "300"))
    block = 1600
    frames: list[bytes] = []
    state = {"speech": False, "silence": 0.0, "blocks": 0}

    def callback(indata: bytes, frame_count: int, time_info: object, status: object) -> None:
        raw = bytes(indata)
        frames.append(raw)
        samples = memoryview(raw).cast("h")
        if not samples:
            return
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        state["blocks"] += 1
        if rms >= limit:
            state["speech"] = True
            state["silence"] = 0.0
        elif state["speech"]:
            state["silence"] += frame_count / samplerate

    try:
        stream = sd.RawInputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
            blocksize=block,
            device=device,
            callback=callback,
        )
    except Exception as exc:
        raise VoiceError(f"could not open the microphone: {exc}") from exc

    with stream:
        deadline = time.monotonic() + max_seconds
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                break
            if state["speech"] and state["silence"] >= silence_seconds:
                break
            time.sleep(0.05)

    data = b"".join(frames)
    if not data:
        raise VoiceError("no audio was captured")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(samplerate)
        handle.writeframes(data)
    return path, bool(state["speech"])


def capture_push(
    model_size: str = "small",
    language: str = "auto",
    *,
    stop_event: threading.Event | None = None,
    max_seconds: float = 20.0,
    keep_audio: bool = False,
) -> tuple[str, Path]:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="akki-", delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        recorded, _had_speech = record_until_silence(
            path,
            stop_event=stop_event,
            max_seconds=max_seconds,
        )
        return transcribe(recorded, model_size, language), recorded
    finally:
        if not keep_audio:
            path.unlink(missing_ok=True)


def listen_push(
    model_size: str = "small",
    language: str = "auto",
    *,
    stop_event: threading.Event | None = None,
    max_seconds: float = 20.0,
) -> str:
    transcript, _path = capture_push(
        model_size,
        language,
        stop_event=stop_event,
        max_seconds=max_seconds,
    )
    return transcript


def _bin_root() -> Path:
    path = database_path().parent / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def piper_exe() -> Path | None:
    override = os.environ.get("AKKI_PIPER")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    for candidate in (
        _bin_root() / "piper" / "piper.exe",
        _bin_root() / "piper.exe",
    ):
        if candidate.is_file():
            return candidate
    found = shutil.which("piper")
    return Path(found) if found else None


def piper_voice_urls(voice: str) -> tuple[str, str]:
    voice = resolve_voice_id(voice)
    parts = voice.split("-")
    if len(parts) != 3 or "_" not in parts[0]:
        raise VoiceError(
            f"invalid piper voice id {voice!r}; expected something like en_US-lessac-medium"
        )
    locale, name, quality = parts
    language = locale.split("_")[0]
    base = f"{PIPER_VOICES_URL}/{language}/{locale}/{name}/{quality}/{voice}"
    return base + ".onnx", base + ".onnx.json"


def piper_voice_paths(voice: str) -> tuple[Path, Path]:
    voice = resolve_voice_id(voice)
    directory = database_path().parent / "models" / "piper"
    return directory / f"{voice}.onnx", directory / f"{voice}.onnx.json"


def piper_python_available() -> bool:
    return importlib.util.find_spec("piper") is not None


def piper_ready(voice: str = DEFAULT_PIPER_VOICE) -> bool:
    model, config = piper_voice_paths(voice)
    backend = piper_exe() is not None or piper_python_available()
    return backend and model.is_file() and config.is_file()


def piper_num_speakers(voice: str = DEFAULT_PIPER_VOICE) -> int:
    _, config = piper_voice_paths(voice)
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 1
    try:
        return max(1, int(data.get("num_speakers", 1)))
    except (TypeError, ValueError):
        return 1


def _download(url: str, target: Path, progress: Progress | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "AKKI"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total, target.name)
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def _extract_zip(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                continue
            destination = (root / member).resolve()
            if root not in destination.parents and destination != root:
                continue
            zf.extract(info, root)


def ensure_piper(
    voice: str = DEFAULT_PIPER_VOICE, progress: Progress | None = None
) -> None:
    if piper_exe() is None and not piper_python_available():
        archive = _bin_root() / "piper_windows_amd64.zip"
        if not archive.is_file():
            _download(PIPER_RELEASE_URL, archive, progress)
        _extract_zip(archive, _bin_root())
        archive.unlink(missing_ok=True)
    if piper_exe() is None and not piper_python_available():
        raise VoiceError("piper executable was not found after installation")

    model, config = piper_voice_paths(voice)
    if not model.is_file():
        url, _ = piper_voice_urls(voice)
        _download(url, model, progress)
    if not config.is_file():
        _, url = piper_voice_urls(voice)
        _download(url, config, progress)


def piper_command(
    exe: Path,
    model: Path,
    config: Path,
    output: Path,
    length_scale: float,
    speaker: int | None = None,
) -> list[str]:
    command = [
        str(exe),
        "--model",
        str(model),
        "--config",
        str(config),
        "--output_file",
        str(output),
        "--length_scale",
        str(max(0.1, float(length_scale))),
    ]
    if speaker is not None:
        command.extend(["--speaker", str(int(speaker))])
    return command


def piper_python_command(
    model: Path,
    config: Path,
    text_file: Path,
    output: Path,
    length_scale: float,
    speaker: int | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "piper",
        "-m",
        str(model),
        "-c",
        str(config),
        "-i",
        str(text_file),
        "-f",
        str(output),
        "--length-scale",
        str(max(0.1, float(length_scale))),
    ]
    if speaker is not None:
        command.extend(["-s", str(int(speaker))])
    return command


def _run_piper_synthesis(
    command: list[str],
    output: Path,
    timeout: float,
    *,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> None:
    try:
        result = subprocess.run(
            command,
            input=stdin,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            **NO_WINDOW_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoiceError(f"piper failed: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or b"").decode(
            "utf-8", errors="replace"
        )
        raise VoiceError(f"piper failed: {detail.strip() or result.returncode}")
    if not output.is_file():
        raise VoiceError("piper produced no audio")


def _load_piper_voice(model: Path, config: Path) -> Any:
    from piper import PiperVoice

    key = (str(model.resolve()), str(config.resolve()))
    with _PIPER_LOCK:
        cached = _PIPER_VOICE_CACHE.get(key)
        if cached is None:
            cached = PiperVoice.load(model, config_path=config)
            _PIPER_VOICE_CACHE[key] = cached
        return cached


def _synthesize_with_python(
    text: str,
    model: Path,
    config: Path,
    output: Path,
    length_scale: float,
    speaker: int | None,
    timeout: float,
) -> None:
    del timeout
    try:
        from piper import SynthesisConfig
    except ImportError as exc:
        raise VoiceError(
            "piper python package is not installed; run :voice setup"
        ) from exc
    try:
        engine = _load_piper_voice(model, config)
        synthesis = SynthesisConfig(
            speaker_id=speaker,
            length_scale=max(0.1, float(length_scale)),
        )
        with _PIPER_LOCK:
            with wave.open(str(output), "wb") as wav:
                engine.synthesize_wav(text, wav, synthesis)
    except VoiceError:
        raise
    except Exception as exc:
        raise VoiceError(f"piper failed: {exc}") from exc
    if not output.is_file():
        raise VoiceError("piper produced no audio")


def _apply_piper_pitch(path: Path, pitch: int) -> None:
    if not pitch:
        return
    try:
        import numpy as np
    except ImportError as exc:
        raise VoiceError(
            "pitch shifting needs numpy: pip install numpy"
        ) from exc
    amount = max(-50, min(50, int(pitch)))
    factor = max(0.5, min(1.5, 1.0 + amount / 100.0))
    with wave.open(str(path), "rb") as reader:
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)
    length = samples.shape[0]
    if length < 2:
        return
    target = max(2, int(round(length / factor)))
    old_axis = np.arange(length, dtype=np.float64)
    new_axis = np.linspace(0, length - 1, target)
    if channels == 1:
        shifted = np.interp(new_axis, old_axis, samples).astype(np.int16)
    else:
        shifted = np.stack(
            [
                np.interp(new_axis, old_axis, samples[:, channel])
                for channel in range(channels)
            ],
            axis=1,
        ).astype(np.int16)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(shifted.tobytes())


def _speech_chunks(text: str, max_chars: int = 140) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    for sentence in sentences:
        remaining = sentence.strip()
        if not remaining:
            continue
        while len(remaining) > max_chars:
            cut = max(
                remaining.rfind(", ", 0, max_chars),
                remaining.rfind("; ", 0, max_chars),
                remaining.rfind(": ", 0, max_chars),
                remaining.rfind(" ", 0, max_chars),
            )
            if cut <= 0:
                cut = max_chars
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
    return chunks or [text]


def _speak_piper_chunked(
    text: str,
    model: Path,
    config: Path,
    length_scale: float,
    speaker: int | None,
    pitch: int,
    timeout: float,
) -> None:
    import queue

    chunks = _speech_chunks(text)
    pending: queue.Queue = queue.Queue()
    errors: list[Exception] = []

    def play() -> None:
        while True:
            item = pending.get()
            if item is None:
                return
            try:
                import winsound

                winsound.PlaySound(str(item), winsound.SND_FILENAME)
            except Exception as exc:
                errors.append(exc)
                return
            finally:
                item.unlink(missing_ok=True)

    player = threading.Thread(target=play, name="akki-tts-play", daemon=True)
    player.start()
    files: list[Path] = []
    try:
        for chunk in chunks:
            if errors:
                break
            handle = tempfile.NamedTemporaryFile(
                suffix=".wav", prefix="akki-", delete=False
            )
            handle.close()
            output = Path(handle.name)
            files.append(output)
            _synthesize_with_python(
                chunk, model, config, output, length_scale, speaker, timeout
            )
            _apply_piper_pitch(output, pitch)
            pending.put(output)
    finally:
        pending.put(None)
        player.join()
        for output in files:
            output.unlink(missing_ok=True)
    if errors:
        raise VoiceError(f"could not play audio: {errors[0]}") from errors[0]


def speak_piper(
    text: str,
    voice: str = DEFAULT_PIPER_VOICE,
    length_scale: float = 1.0,
    timeout: float = 120.0,
    speaker: int | None = None,
    pitch: int = 0,
) -> None:
    text = clean_for_speech(text)
    if not text:
        return
    if os.name != "nt":
        raise VoiceError("piper playback is only available on Windows")
    model, config = piper_voice_paths(voice)
    if not model.is_file() or not config.is_file():
        raise VoiceError(f"piper voice {voice} is missing; run :voice setup")
    exe = piper_exe()
    python_available = piper_python_available()
    if exe is None and not python_available:
        raise VoiceError("piper is not installed; run :voice setup")

    if python_available:
        _speak_piper_chunked(
            text, model, config, length_scale, speaker, pitch, timeout
        )
        return

    assert exe is not None
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="akki-", delete=False)
    handle.close()
    output = Path(handle.name)
    try:
        _run_piper_synthesis(
            piper_command(exe, model, config, output, length_scale, speaker),
            output,
            timeout,
            stdin=text.encode("utf-8"),
            cwd=str(exe.parent),
        )
        _apply_piper_pitch(output, pitch)
        try:
            import winsound

            winsound.PlaySound(str(output), winsound.SND_FILENAME)
        except RuntimeError as exc:
            raise VoiceError(f"could not play audio: {exc}") from exc
    finally:
        output.unlink(missing_ok=True)


def prewarm_piper(
    voice: str = DEFAULT_PIPER_VOICE,
    length_scale: float = 1.0,
    speaker: int | None = None,
) -> None:
    """Load and warm the Piper model so the next reply can start quickly."""
    if not piper_python_available():
        return
    model, config = piper_voice_paths(voice)
    if not model.is_file() or not config.is_file():
        return
    handle = tempfile.NamedTemporaryFile(
        suffix=".wav", prefix="akki-warm-", delete=False
    )
    handle.close()
    output = Path(handle.name)
    try:
        _synthesize_with_python(
            "Ready.", model, config, output, length_scale, speaker, 120.0
        )
    except VoiceError:
        pass
    finally:
        output.unlink(missing_ok=True)
