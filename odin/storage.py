from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_expiry ON cache(expires_at);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
    note TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL DEFAULT '',
    response TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating, id);
"""


def make_cache_key(
    provider: str,
    model: str,
    system: str,
    history: list[dict[str, str]],
    text: str,
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "system": system,
            "history": history,
            "text": text,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Storage:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def start_session(self) -> int:
        now = time.time()
        cursor = self._db.execute(
            "INSERT INTO sessions(started_at) VALUES (?)", (now,)
        )
        self._db.commit()
        return int(cursor.lastrowid)

    def add_turn(self, session_id: int, role: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO turns(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        self._db.commit()

    def recent_turns(
        self, limit: int = 20, session_id: int | None = None
    ) -> list[tuple[str, str]]:
        if session_id is None:
            rows = self._db.execute(
                "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT role, content FROM turns WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [(row["role"], row["content"]) for row in reversed(rows)]

    def remember(self, fact: str) -> int:
        normalized = " ".join(fact.split())
        if not normalized:
            raise ValueError("memory fact cannot be empty")
        self._db.execute(
            "INSERT INTO memories(fact, created_at) VALUES (?, ?) "
            "ON CONFLICT(fact) DO NOTHING",
            (normalized, time.time()),
        )
        self._db.commit()
        row = self._db.execute(
            "SELECT id FROM memories WHERE fact = ?", (normalized,)
        ).fetchone()
        return int(row["id"])

    def memories(self) -> list[tuple[int, str]]:
        rows = self._db.execute(
            "SELECT id, fact FROM memories ORDER BY id"
        ).fetchall()
        return [(int(row["id"]), row["fact"]) for row in rows]

    def forget(self, memory_id: int) -> bool:
        cursor = self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._db.commit()
        return cursor.rowcount > 0

    def cache_get(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        if float(row["expires_at"]) <= time.time():
            self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._db.commit()
            return None
        return str(row["value"])

    def cache_put(self, key: str, value: str, ttl_seconds: float) -> None:
        now = time.time()
        self._db.execute(
            "INSERT OR REPLACE INTO cache(key, value, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (key, value, now, now + max(0.0, ttl_seconds)),
        )
        self._db.commit()

    def purge_cache(self, expired_only: bool = True) -> int:
        if expired_only:
            cursor = self._db.execute(
                "DELETE FROM cache WHERE expires_at <= ?", (time.time(),)
            )
        else:
            cursor = self._db.execute("DELETE FROM cache")
        self._db.commit()
        return cursor.rowcount

    def cache_stats(self) -> dict[str, Any]:
        total_row = self._db.execute("SELECT COUNT(*) AS n FROM cache").fetchone()
        expired_row = self._db.execute(
            "SELECT COUNT(*) AS n FROM cache WHERE expires_at <= ?", (time.time(),)
        ).fetchone()
        return {"entries": int(total_row["n"]), "expired": int(expired_row["n"])}

    def add_feedback(
        self,
        rating: int,
        *,
        note: str = "",
        prompt: str = "",
        response: str = "",
        session_id: int | None = None,
    ) -> int:
        if rating not in {-1, 1}:
            raise ValueError("feedback rating must be 1 or -1")
        cursor = self._db.execute(
            "INSERT INTO feedback(session_id, rating, note, prompt, response, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                rating,
                " ".join(note.split()),
                prompt,
                response,
                time.time(),
            ),
        )
        self._db.commit()
        return int(cursor.lastrowid)

    def recent_feedback(
        self, limit: int = 6, rating: int | None = None
    ) -> list[dict[str, Any]]:
        if rating is None:
            rows = self._db.execute(
                "SELECT id, session_id, rating, note, prompt, response, created_at "
                "FROM feedback ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id, session_id, rating, note, prompt, response, created_at "
                "FROM feedback WHERE rating = ? ORDER BY id DESC LIMIT ?",
                (rating, limit),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "session_id": row["session_id"],
                "rating": int(row["rating"]),
                "note": str(row["note"]),
                "prompt": str(row["prompt"]),
                "response": str(row["response"]),
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ]

    def feedback_stats(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT rating, COUNT(*) AS n FROM feedback GROUP BY rating"
        ).fetchall()
        counts = {int(row["rating"]): int(row["n"]) for row in rows}
        positive = counts.get(1, 0)
        negative = counts.get(-1, 0)
        return {
            "positive": positive,
            "negative": negative,
            "total": positive + negative,
            "score": positive - negative,
        }

    def clear_feedback(self) -> int:
        cursor = self._db.execute("DELETE FROM feedback")
        self._db.commit()
        return cursor.rowcount
