from __future__ import annotations

import json
import math
import wave
from pathlib import Path
from typing import Any

import numpy as np

from .storage import Storage


class SpeakerError(RuntimeError):
    pass


def _embed_audio(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise SpeakerError("speaker audio must be 16-bit PCM WAV")
        channels = handle.getnchannels()
        frames = handle.getnframes()
        rate = handle.getframerate()
        raw = handle.readframes(frames)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        usable = samples.size // channels
        samples = samples[: usable * channels].reshape(-1, channels).mean(axis=1)
    if samples.size < int(0.05 * rate):
        raise SpeakerError("speaker audio is too short")
    window = max(1, int(0.025 * rate))
    hop = max(1, int(0.010 * rate))
    vectors: list[list[float]] = []
    for start in range(0, samples.size - window + 1, hop):
        frame = samples[start : start + window]
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        zero_crossings = float(np.sum(np.diff(np.signbit(frame)) != 0))
        spectrum = np.abs(np.fft.rfft(frame.astype(np.float64)))
        freqs = np.fft.rfftfreq(window, d=1.0 / rate)
        centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-12))
        vectors.append(
            [
                math.log1p(rms),
                zero_crossings / max(1, len(frame)),
                math.log1p(centroid),
                float(len(frame)),
            ]
        )
    matrix = np.asarray(vectors, dtype=np.float64)
    embedding = matrix.mean(axis=0)
    norm = float(np.linalg.norm(embedding))
    if norm <= 1e-9:
        embedding = np.zeros_like(embedding)
    return [float(value) for value in embedding / norm]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a)) or 1.0
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def enroll_speaker(
    storage: Storage, name: str, audio_path: Path | str
) -> int:
    cleaned = name.strip()
    if not cleaned:
        raise SpeakerError("speaker name cannot be empty")
    embedding = _embed_audio(Path(audio_path))
    cursor = storage.db.execute(
        "INSERT INTO speakers(name, embedding, created_at) VALUES (?, ?, ?)",
        (cleaned, json.dumps(embedding), __import__("time").time()),
    )
    storage.db.commit()
    row = storage.db.execute(
        "SELECT id FROM speakers WHERE name = ?", (cleaned,)
    ).fetchone()
    return int(row["id"])


def list_speakers(storage: Storage) -> list[dict[str, Any]]:
    rows = storage.db.execute(
        "SELECT id, name, embedding, created_at FROM speakers ORDER BY id"
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "embedding": json.loads(str(row["embedding"])),
            "created_at": float(row["created_at"]),
        }
        for row in rows
    ]


def forget_speaker(storage: Storage, name: str) -> bool:
    cursor = storage.db.execute(
        "DELETE FROM speakers WHERE name = ?", (name.strip(),)
    )
    storage.db.commit()
    return cursor.rowcount > 0


def identify_speaker(
    storage: Storage,
    audio_path: Path | str,
    threshold: float = 0.7,
) -> dict[str, Any] | None:
    embedding = _embed_audio(Path(audio_path))
    best: dict[str, Any] | None = None
    best_similarity = 0.0
    for speaker in list_speakers(storage):
        similarity = _cosine(embedding, speaker["embedding"])
        if similarity > best_similarity:
            best_similarity = similarity
            best = speaker
    if best is None or best_similarity < threshold:
        return None
    return {
        "speaker_id": int(best["id"]),
        "speaker": str(best["name"]),
        "similarity": float(best_similarity),
    }
