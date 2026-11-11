from __future__ import annotations

import base64
import importlib.util
import json
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
from typing import Callable

from .config import database_path

PIPER_RELEASE_URL = (
    "https://github.com/rhasspy/piper/releases/download/"
    "2023.11.14-2/piper_windows_amd64.zip"
)
PIPER_VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"

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
    value = value.replace("—", ", ").replace("–", ", ")
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"[,;:]{2,}", ",", value)
    value = " ".join(value.split()).strip()
    return value.strip(" -")


def piper_catalog() -> list[tuple[str, str]]:
    return list(PIPER_CATALOG.items())


class VoiceError(RuntimeError):
    pass


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
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VoiceError(f"powershell failed: {exc}") from exc


def speech_script(
    text: str,
    rate: int = 1,
    volume: int = 100,
    voice_name: str = "",
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
    lines.extend(
        [
            "$text = [Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{payload}'))",
            "$s.Speak($text)",
        ]
    )
    return "\n".join(lines)


def _speak_sapi(
    text: str,
    rate: int = 1,
    volume: int = 100,
    voice_name: str = "",
    timeout: float = 120.0,
) -> None:
    if os.name != "nt":
        raise VoiceError("text-to-speech uses Windows SAPI and is only available on Windows")
    result = _powershell(
        speech_script(text, rate, volume, voice_name), timeout=timeout
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise VoiceError(f"speech synthesis failed: {detail or result.returncode}")


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
) -> None:
    cleaned = clean_for_speech(text)
    if not cleaned:
        return
    engine = engine.strip().lower()
    if engine == "piper":
        speak_piper(cleaned, piper_voice, piper_length_scale, timeout, piper_speaker)
        return
    if engine == "sapi":
        _speak_sapi(cleaned, rate, volume, voice_name, timeout)
        return
    raise VoiceError(f"unknown tts engine: {engine} (use piper or sapi)")


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


def record_to_wav(path: Path, samplerate: int = 16000) -> Path:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceError(
            "recording needs sounddevice: pip install sounddevice"
        ) from exc

    frames: list[bytes] = []

    def callback(indata: bytes, frame_count: int, time_info: object, status: object) -> None:
        frames.append(bytes(indata))

    try:
        stream = sd.RawInputStream(
            samplerate=samplerate,
            channels=1,
            dtype="int16",
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
    model = _whisper_model(model_size)
    detected: str | None = None
    if model_size.endswith(".en"):
        detected = "en"
    elif language and language.lower() != "auto":
        detected = language
    segments, _ = model.transcribe(
        str(path),
        language=detected,
        beam_size=1,
        vad_filter=True,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise VoiceError("could not transcribe any speech")
    return text


def listen(model_size: str = "small", language: str = "auto") -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="odin-", delete=False)
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
) -> Path:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise VoiceError(
            "recording needs sounddevice: pip install sounddevice"
        ) from exc

    limit = threshold
    if limit is None:
        limit = int(os.environ.get("ODIN_MIC_THRESHOLD", "300"))
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
    return path


def listen_push(
    model_size: str = "small",
    language: str = "auto",
    *,
    stop_event: threading.Event | None = None,
    max_seconds: float = 20.0,
) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="odin-", delete=False)
    handle.close()
    path = Path(handle.name)
    try:
        record_until_silence(
            path,
            stop_event=stop_event,
            max_seconds=max_seconds,
        )
        return transcribe(path, model_size, language)
    finally:
        path.unlink(missing_ok=True)


def _bin_root() -> Path:
    path = database_path().parent / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def piper_exe() -> Path | None:
    override = os.environ.get("ODIN_PIPER")
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
    request = urllib.request.Request(url, headers={"User-Agent": "ODIN"})
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


def _synthesize_with_python(
    text: str,
    model: Path,
    config: Path,
    output: Path,
    length_scale: float,
    speaker: int | None,
    timeout: float,
) -> None:
    handle = tempfile.NamedTemporaryFile(suffix=".txt", prefix="odin-", delete=False)
    text_file = Path(handle.name)
    handle.write(text.encode("utf-8"))
    handle.close()
    try:
        _run_piper_synthesis(
            piper_python_command(
                model, config, text_file, output, length_scale, speaker
            ),
            output,
            timeout,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
        )
    finally:
        text_file.unlink(missing_ok=True)


def speak_piper(
    text: str,
    voice: str = DEFAULT_PIPER_VOICE,
    length_scale: float = 1.0,
    timeout: float = 120.0,
    speaker: int | None = None,
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

    handle = tempfile.NamedTemporaryFile(suffix=".wav", prefix="odin-", delete=False)
    handle.close()
    output = Path(handle.name)
    try:
        exe_error: VoiceError | None = None
        if exe is not None:
            try:
                _run_piper_synthesis(
                    piper_command(
                        exe, model, config, output, length_scale, speaker
                    ),
                    output,
                    timeout,
                    stdin=text.encode("utf-8"),
                    cwd=str(exe.parent),
                )
            except VoiceError as exc:
                exe_error = exc
        if exe is None or exe_error is not None:
            if not python_available:
                assert exe_error is not None
                raise exe_error
            _synthesize_with_python(
                text, model, config, output, length_scale, speaker, timeout
            )
        try:
            import winsound

            winsound.PlaySound(str(output), winsound.SND_FILENAME)
        except RuntimeError as exc:
            raise VoiceError(f"could not play audio: {exc}") from exc
    finally:
        output.unlink(missing_ok=True)
