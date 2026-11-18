from __future__ import annotations

import base64
from typing import Any

import numpy as np

from .models import ToolResult
from .storage import Storage


class VisionError(RuntimeError):
    pass


def vision_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def capture_camera() -> ToolResult:
    if not vision_available():
        return ToolResult.failure(
            "camera capture needs opencv-python: pip install opencv-python"
        )
    import cv2

    capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not capture.isOpened():
        return ToolResult.failure("could not open camera")
    grabbed, frame = capture.read()
    if not grabbed or frame is None:
        return ToolResult.failure("could not read a camera frame")
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok or encoded is None:
        return ToolResult.failure("could not encode camera frame")
    image_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
    capture.release()
    return ToolResult.success(
        f"Camera captured {frame.shape[1]}x{frame.shape[0]}",
        data={
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "image_b64": image_b64,
            "bytes": int(len(encoded.tobytes())),
        },
    )


def _decode_image(image_b64: str) -> np.ndarray:
    import cv2

    try:
        data = base64.b64decode(image_b64, validate=True)
    except Exception as exc:
        raise VisionError(f"invalid image encoding: {exc}") from exc
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise VisionError("could not decode image")
    return frame


def detect_faces(image_b64: str) -> list[dict[str, Any]]:
    if not vision_available():
        return []
    import cv2

    frame = _decode_image(image_b64)
    cascade_name = getattr(cv2.data, "haarcascade_frontalface_default", None)
    if not cascade_name:
        return []
    detector = cv2.CascadeClassifier(str(cascade_name))
    if not detector.isOpened():
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    boxes = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
    )
    return [
        {
            "x": int(box[0]),
            "y": int(box[1]),
            "width": int(box[2]),
            "height": int(box[3]),
        }
        for box in boxes
    ]


def enroll_face(storage: Storage, name: str, image_b64: str) -> int:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("face name cannot be empty")
    cursor = storage.db.execute(
        "INSERT INTO faces(name, image_b64, created_at) VALUES (?, ?, ?)",
        (cleaned, image_b64, __import__("time").time()),
    )
    storage.db.commit()
    row = storage.db.execute(
        "SELECT id FROM faces WHERE name = ?", (cleaned,)
    ).fetchone()
    return int(row["id"])


def list_faces(storage: Storage) -> list[dict[str, Any]]:
    rows = storage.db.execute(
        "SELECT id, name, image_b64, created_at FROM faces ORDER BY id"
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "image_b64": str(row["image_b64"]),
            "created_at": float(row["created_at"]),
        }
        for row in rows
    ]


def forget_face(storage: Storage, name: str) -> bool:
    cursor = storage.db.execute(
        "DELETE FROM faces WHERE name = ?", (name.strip(),)
    )
    storage.db.commit()
    return cursor.rowcount > 0
