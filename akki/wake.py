from __future__ import annotations

import difflib
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from . import voice


logger = logging.getLogger("akki.wake")
logger.addHandler(logging.NullHandler())


class WakeWordError(RuntimeError):
    pass


def wake_supported() -> bool:
    return sys.platform == "win32"


def normalize_wake_word(text: str, phrase: str) -> bool:
    wanted = re.sub(r"[^a-z0-9\s]", "", phrase.lower())
    wanted = " ".join(wanted.split())
    heard = re.sub(r"[^a-z0-9\s]", "", text.lower())
    heard = " ".join(heard.split())
    if not wanted:
        return False
    if heard.startswith(wanted) or wanted in heard:
        return True
    wanted_words = wanted.split()
    heard_words = heard.split()
    if not heard_words:
        return False
    size = len(wanted_words)
    if size >= 2 and len(wanted_words[-1]) >= 4:
        if wanted_words[-1] in heard_words:
            return True
        if len(heard_words) == 1:
            return (
                difflib.SequenceMatcher(
                    None, heard_words[0], wanted_words[-1]
                ).ratio()
                >= 0.75
            )
    if len(heard_words) < size:
        return (
            difflib.SequenceMatcher(
                None, " ".join(heard_words), wanted
            ).ratio()
            >= 0.75
        )
    for index in range(len(heard_words) - size + 1):
        window = " ".join(heard_words[index : index + size])
        if difflib.SequenceMatcher(None, window, wanted).ratio() >= 0.75:
            return True
    return False


class WakeWordListener:
    def __init__(
        self,
        callback: Callable[[], None],
        phrase: str = "hey akki",
        model_size: str = "small",
        language: str = "auto",
    ) -> None:
        self.callback = callback
        self.phrase = phrase
        self.model_size = model_size
        self.language = language
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="akki-wake", daemon=True
        )
        self._thread_id: int | None = None
        self.error: str | None = None
        self.active = False

    def start(self, timeout: float = 3.0) -> None:
        if not wake_supported():
            raise WakeWordError("wake-word listening is only available on Windows")
        self._thread.start()
        deadline = time.monotonic() + timeout
        while self._thread_id is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if self._thread_id is None:
            self.stop()
            raise WakeWordError("timed out starting wake-word listener")
        self.active = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(2.0)
        self.active = False

    def _run(self) -> None:
        self._thread_id = id(self)
        last_heartbeat = time.monotonic()
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_heartbeat >= 20:
                    logger.info("wake listener alive")
                    last_heartbeat = now
                handle = __import__("tempfile").NamedTemporaryFile(
                    suffix=".wav", prefix="akki-wake-", delete=False
                )
                path = Path(handle.name)
                handle.close()
                try:
                    recorded, had_speech = voice.record_until_silence(
                        path,
                        stop_event=self._stop_event,
                        max_seconds=3.0,
                    )
                    if not had_speech:
                        logger.debug("wake pass: silence")
                        continue
                    logger.info("wake speech detected")
                    transcript = voice.transcribe(
                        recorded, self.model_size, self.language
                    )
                    logger.info("wake transcript=%r", transcript)
                    if normalize_wake_word(transcript, self.phrase):
                        logger.info("wake phrase detected")
                        self.callback()
                        return
                except Exception as exc:  # noqa: BLE001
                    self.error = str(exc)
                    logger.debug("wake listening pass failed: %s", exc)
                    self._stop_event.wait(0.2)
                finally:
                    path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        finally:
            self.active = False
