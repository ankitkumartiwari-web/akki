from __future__ import annotations

import io
import logging
import math
import os
import queue
import struct
import tempfile
import threading
import wave
from collections.abc import Callable
from functools import lru_cache
from typing import Any

logger = logging.getLogger("akki.indicator")

TRANSPARENT = "#010203"
TRANSPARENT_RGB = (1, 2, 3)
ORB_DISPLAY_SIZE = 72
ORB_RENDER_SIZE = 384
ORB_FRAME_COUNT = 48
ORB_FRAME_MS = 50
HALO_BACKGROUND = (5, 8, 24)
ORB_PARTICLE_COUNT = 3600
BUBBLE_MARGIN = 24
BUBBLE_TOP = 24


@lru_cache(maxsize=1)
def _orb_particle_seeds() -> tuple[Any, Any, Any, Any, Any, Any]:
    import numpy as np

    index = np.arange(ORB_PARTICLE_COUNT, dtype=np.float32)
    z = 1.0 - 2.0 * (index + 0.5) / ORB_PARTICLE_COUNT
    longitude = index * np.float32(math.pi * (3.0 - math.sqrt(5.0)))
    latitude = np.arcsin(z)
    random = np.random.default_rng(814).random
    phase_offset = random(ORB_PARTICLE_COUNT, dtype=np.float32) * math.tau
    brightness = random(ORB_PARTICLE_COUNT, dtype=np.float32)
    size_variation = random(ORB_PARTICLE_COUNT, dtype=np.float32)
    dispersion = random(ORB_PARTICLE_COUNT, dtype=np.float32) > 0.965
    return longitude, latitude, phase_offset, brightness, size_variation, dispersion


def listen_sound_wav(
    rate: int = 22050,
    duration: float = 0.07,
    lead_silence: float = 0.25,
) -> bytes:
    frames = bytearray(struct.pack("<h", 0) * int(rate * lead_silence))
    count = max(1, int(rate * duration))
    for index in range(count):
        progress = index / count
        frequency = 520.0 + 420.0 * progress
        envelope = (1.0 - progress) ** 2
        sample = 0.60 * 32767.0 * envelope * math.sin(
            2.0 * math.pi * frequency * index / rate
        )
        frames += struct.pack("<h", int(sample))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def bubble_geometry(screen_width: int) -> str:
    x = max(0, screen_width - ORB_DISPLAY_SIZE - BUBBLE_MARGIN)
    return f"{ORB_DISPLAY_SIZE}x{ORB_DISPLAY_SIZE}+{x}+{BUBBLE_TOP}"


def render_orb_base(size: int, phase: float = 0.0) -> Any:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    phase %= 2.0 * math.pi
    palette = np.asarray(
        [
            (18, 30, 164),
            (24, 102, 255),
            (42, 226, 255),
            (64, 128, 255),
            (137, 68, 255),
            (245, 82, 222),
        ],
        dtype=np.float32,
    )
    coral = np.asarray((255, 110, 75), dtype=np.float32)
    pink = np.asarray((255, 185, 225), dtype=np.float32)

    def energy_color(longitude: Any, latitude: Any) -> Any:
        u = np.asarray(longitude, dtype=np.float32)
        v = np.asarray(latitude, dtype=np.float32)
        hue = np.clip(
            0.5
            + 0.5
            * np.sin(
                1.5 * u
                - 2.0 * v
                + 0.55 * np.sin(2.0 * u + v + phase)
            ),
            0.0,
            1.0,
        )
        scaled = hue * (len(palette) - 1)
        low = np.floor(scaled).astype(np.int32)
        high = np.minimum(low + 1, len(palette) - 1)
        blend = (scaled - low)[..., None]
        cool = palette[low] * (1.0 - blend) + palette[high] * blend
        warm_wave = 0.5 + 0.5 * np.sin(
            2.1 * u
            + 2.7 * v
            + 0.75 * np.sin(3.0 * u - phase)
            + phase
        )
        warm = np.clip((warm_wave - 0.83) / 0.17, 0.0, 1.0)
        warm_blend = 0.5 + 0.5 * np.sin(1.4 * u + v + phase)
        warm_color = coral * (1.0 - warm_blend[..., None])
        warm_color += pink * warm_blend[..., None]
        return cool * (1.0 - warm[..., None]) + warm_color * warm[..., None]

    def deform(longitude: Any, latitude: Any, layer: float = 0.0) -> tuple[Any, Any, Any]:
        wave_a = np.sin(
            2.0 * longitude + 3.0 * latitude + phase + layer
        )
        wave_b = np.cos(
            4.0 * longitude - 2.0 * latitude - 2.0 * phase + 1.3 * layer
        )
        radial = (
            0.86
            + 0.052 * wave_a
            + 0.032 * wave_b
            + 0.018
            * np.sin(
                5.0 * longitude - 4.0 * latitude - 2.0 * phase + layer
            )
        )
        x = (
            np.cos(latitude) * np.cos(longitude) * radial
            + 0.035
            * np.sin(2.0 * longitude + latitude - 2.0 * phase + layer)
        )
        y = (
            np.sin(latitude) * radial
            + 0.035 * np.sin(3.0 * longitude - 2.0 * phase + layer)
        )
        z = (
            np.cos(latitude) * np.sin(longitude) * radial
            + 0.04
            * np.cos(2.0 * longitude + 3.0 * latitude + phase + layer)
        )
        return x, y, z

    def project(x: Any, y: Any, z: Any) -> tuple[Any, Any]:
        perspective = 1.0 / (1.34 - 0.18 * z)
        scale = size * 0.46
        px = np.rint(size * 0.5 + x * perspective * scale).astype(np.int32)
        py = np.rint(size * 0.5 - y * perspective * scale).astype(np.int32)
        return px, py

    def rgb(color: Any) -> tuple[int, int, int]:
        values = np.clip(np.rint(color), 0, 255).astype(np.uint8)
        return int(values[0]), int(values[1]), int(values[2])

    mesh_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mesh_draw = ImageDraw.Draw(mesh_layer, "RGBA")
    glow_draw = ImageDraw.Draw(glow_layer, "RGBA")

    def draw_curve(
        drawer: Any,
        glow: Any,
        px: Any,
        py: Any,
        color: Any,
        alpha: int,
        width: int = 1,
        bloom: bool = False,
    ) -> None:
        points = list(zip(px.tolist(), py.tolist()))
        if len(points) < 2:
            return
        color_rgb = rgb(color)
        drawer.line(points, fill=(*color_rgb, alpha), width=width)
        if bloom:
            glow_color = tuple(
                int(component * 0.55 + 255 * 0.45) for component in color_rgb
            )
            glow.line(
                points,
                fill=(*glow_color, min(255, alpha + 50)),
                width=max(3, width * 2),
            )

    lat_samples = np.linspace(-1.42, 1.42, 96, dtype=np.float32)
    for index, longitude in enumerate(
        np.linspace(0.0, math.tau, 36, endpoint=False)
    ):
        u = np.full_like(lat_samples, longitude)
        x, y, z = deform(u, lat_samples)
        px, py = project(x, y, z)
        front = math.sin(longitude) > 0.0
        color = energy_color(longitude, float(np.mean(lat_samples)))
        alpha = 42 + int(92 * max(0.0, math.sin(longitude)))
        draw_curve(
            mesh_draw,
            glow_draw,
            px,
            py,
            color,
            alpha,
            width=3 if front else 1,
            bloom=front and index % 2 == 0,
        )

    longitude_samples = np.linspace(
        0.0, math.tau, 192, endpoint=True, dtype=np.float32
    )
    split = len(longitude_samples) // 2
    for index, latitude in enumerate(
        np.linspace(-1.28, 1.28, 24, dtype=np.float32)
    ):
        v = np.full_like(longitude_samples, latitude)
        x, y, z = deform(longitude_samples, v)
        px, py = project(x, y, z)
        color = energy_color(float(index) * 0.23, float(latitude))
        draw_curve(
            mesh_draw,
            glow_draw,
            px[: split + 1],
            py[: split + 1],
            color,
            128,
            width=2,
            bloom=index % 4 == 0,
        )
        draw_curve(
            mesh_draw,
            glow_draw,
            px[split:],
            py[split:],
            color,
            38,
            width=1,
        )

    ribbon_u = np.linspace(0.0, math.tau, 192, endpoint=True, dtype=np.float32)
    ribbon_specs = (
        (-0.20, 0.18, 0.2),
        (0.24, 0.15, 1.6),
        (0.53, 0.12, 3.0),
        (-0.54, 0.11, 4.5),
    )
    for ribbon_index, (center, width, offset) in enumerate(ribbon_specs):
        ribbon_center = (
            center
            + 0.42 * np.sin(2.0 * ribbon_u + phase + offset)
            + 0.14 * np.sin(3.0 * ribbon_u - 2.0 * phase + offset)
        )
        ribbon_width = width * (
            0.68
            + 0.32
            * (0.5 + 0.5 * np.sin(2.5 * ribbon_u + phase + offset))
        )
        upper = np.clip(ribbon_center + ribbon_width, -1.42, 1.42)
        lower = np.clip(ribbon_center - ribbon_width, -1.42, 1.42)
        upper_x, upper_y, upper_z = deform(ribbon_u, upper, offset)
        lower_x, lower_y, lower_z = deform(ribbon_u, lower, offset)
        upper_px, upper_py = project(upper_x, upper_y, upper_z)
        lower_px, lower_py = project(lower_x, lower_y, lower_z)

        segment_count = 12
        for segment in range(segment_count):
            start = segment * (len(ribbon_u) - 1) // segment_count
            end = (segment + 1) * (len(ribbon_u) - 1) // segment_count + 1
            points = list(zip(upper_px[start:end].tolist(), upper_py[start:end].tolist()))
            points.extend(
                zip(
                    lower_px[start:end][::-1].tolist(),
                    lower_py[start:end][::-1].tolist(),
                )
            )
            color = energy_color(
                float((ribbon_u[start] + ribbon_u[end - 1]) * 0.5),
                float((ribbon_center[start] + ribbon_center[end - 1]) * 0.5),
            )
            mesh_draw.polygon(points, fill=(*rgb(color), 28))

        for grid_line in range(7):
            fraction = grid_line / 6.0
            latitude = lower * (1.0 - fraction) + upper * fraction
            x, y, z = deform(ribbon_u, latitude, offset)
            px, py = project(x, y, z)
            mid = len(ribbon_u) // 2
            front_color = energy_color(
                float(ribbon_u[mid]),
                float(ribbon_center[mid]),
            )
            alpha = 128 + int(52 * max(0.0, float(np.mean(z))))
            draw_curve(
                mesh_draw,
                glow_draw,
                px[: mid + 1],
                py[: mid + 1],
                front_color,
                alpha,
                width=2,
                bloom=grid_line in (1, 3, 5),
            )
            draw_curve(
                mesh_draw,
                glow_draw,
                px[mid:],
                py[mid:],
                front_color,
                24,
                width=1,
            )

        for sample in range(8, len(ribbon_u), 16):
            latitude = np.linspace(
                lower[sample], upper[sample], 12, dtype=np.float32
            )
            longitude = np.full_like(latitude, ribbon_u[sample])
            x, y, z = deform(longitude, latitude, offset)
            px, py = project(x, y, z)
            color = energy_color(
                float(ribbon_u[sample]), float(ribbon_center[sample])
            )
            draw_curve(
                mesh_draw,
                glow_draw,
                px,
                py,
                color,
                96 if math.sin(float(ribbon_u[sample])) > 0.0 else 34,
            )

    (
        particle_longitude,
        particle_latitude,
        particle_phase,
        particle_brightness,
        size_variation,
        dispersion,
    ) = _orb_particle_seeds()
    particle_count = max(
        1,
        round(ORB_PARTICLE_COUNT * (size / ORB_RENDER_SIZE) ** 2),
    )
    particle_longitude = particle_longitude[:particle_count]
    particle_latitude = particle_latitude[:particle_count]
    particle_phase = particle_phase[:particle_count]
    particle_brightness = particle_brightness[:particle_count]
    size_variation = size_variation[:particle_count]
    dispersion = dispersion[:particle_count]
    u = (
        particle_longitude
        + 0.035 * np.sin(2.0 * phase + particle_phase)
        + 0.012 * np.sin(3.0 * particle_longitude + phase)
    )
    v = (
        particle_latitude
        + 0.03 * np.sin(3.0 * phase - particle_phase)
        + 0.01 * np.cos(4.0 * particle_latitude + 2.0 * phase)
    )
    x, y, z = deform(u, v, 0.4)
    drift = dispersion.astype(np.float32) * (
        0.06
        + 0.08 * (0.5 + 0.5 * np.sin(3.0 * phase + particle_phase))
    )
    x *= 1.0 + drift
    y *= 1.0 + drift
    z *= 1.0 + drift
    particle_x, particle_y = project(x, y, z)
    visible = (
        (particle_x >= 2)
        & (particle_x < size - 2)
        & (particle_y >= 2)
        & (particle_y < size - 2)
    )
    colors = energy_color(u, v)
    depth = np.clip(0.42 + 0.58 * (z + 1.0) * 0.5, 0.0, 1.0)
    twinkle = 0.5 + 0.5 * np.sin(
        3.0 * phase + particle_phase + particle_brightness * math.tau
    )
    intensity = (
        (0.28 + 0.72 * particle_brightness)
        * (0.46 + 0.54 * depth)
        * (0.52 + 0.48 * twinkle)
    )
    opacity = np.clip(35.0 + 210.0 * intensity, 35.0, 245.0)
    particle_perspective = 1.0 / (1.34 - 0.18 * z)
    particle_scale = size * 0.46
    particle_x_float = size * 0.5 + x * particle_perspective * particle_scale
    particle_y_float = size * 0.5 - y * particle_perspective * particle_scale
    particle_x0 = np.floor(particle_x_float).astype(np.int32)
    particle_y0 = np.floor(particle_y_float).astype(np.int32)
    visible &= (
        (particle_x0 >= 1)
        & (particle_x0 < size - 2)
        & (particle_y0 >= 1)
        & (particle_y0 < size - 2)
    )
    fraction_x = particle_x_float - particle_x0
    fraction_y = particle_y_float - particle_y0
    particle_alpha = np.zeros((size, size), dtype=np.float32)
    particle_color = np.zeros((size, size, 3), dtype=np.float32)
    particle_weight = opacity / 255.0
    splats = (
        (0, 0, (1.0 - fraction_x) * (1.0 - fraction_y)),
        (1, 0, fraction_x * (1.0 - fraction_y)),
        (0, 1, (1.0 - fraction_x) * fraction_y),
        (1, 1, fraction_x * fraction_y),
    )
    for offset_x, offset_y, coverage in splats:
        indices = visible
        x_indices = particle_x0[indices] + offset_x
        y_indices = particle_y0[indices] + offset_y
        weights = particle_weight[indices] * coverage[indices]
        np.add.at(particle_alpha, (y_indices, x_indices), weights)
        for channel in range(3):
            np.add.at(
                particle_color[..., channel],
                (y_indices, x_indices),
                colors[indices, channel] * weights,
            )
    particle_rgb = np.divide(
        particle_color,
        particle_alpha[..., None],
        out=np.zeros_like(particle_color),
        where=particle_alpha[..., None] > 0.0,
    )
    particle_alpha = (1.0 - np.exp(-particle_alpha * 1.25)) * 255.0
    particle_pixels = np.dstack([particle_rgb, particle_alpha]).astype(np.uint8)
    particle_layer = Image.fromarray(particle_pixels, "RGBA")
    particle_draw = ImageDraw.Draw(particle_layer, "RGBA")

    sparks = np.flatnonzero(
        visible & (size_variation > 0.86) & (intensity > 0.5)
    )
    for spark in sparks:
        px = int(round(float(particle_x_float[spark])))
        py = int(round(float(particle_y_float[spark])))
        color = rgb(colors[spark] * 0.7 + 255.0 * 0.3)
        radius = max(
            1,
            int(
                round(
                    (3.0 + size_variation[spark])
                    * size
                    / ORB_RENDER_SIZE
                )
            ),
        )
        alpha = int(opacity[spark])
        particle_draw.ellipse(
            (px - radius, py - radius, px + radius, py + radius),
            fill=(*color, alpha),
        )

    glow_radius = max(1.0, size * 0.012)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_radius))
    glow_layer.putalpha(
        glow_layer.getchannel("A").point(lambda alpha: alpha * 3 // 4)
    )
    particle_glow = particle_layer.filter(
        ImageFilter.GaussianBlur(max(0.8, size * 0.007))
    )
    particle_glow.putalpha(
        particle_glow.getchannel("A").point(lambda alpha: alpha * 3 // 4)
    )
    frame = Image.alpha_composite(glow_layer, mesh_layer)
    frame = Image.alpha_composite(frame, particle_glow)
    frame = Image.alpha_composite(frame, particle_layer)
    pixels = np.asarray(frame).copy()
    pixels[pixels[..., 3] == 0, :3] = TRANSPARENT_RGB
    return Image.fromarray(pixels, "RGBA")


def build_orb_frames(
    size: int = ORB_RENDER_SIZE, count: int = ORB_FRAME_COUNT
) -> list[Any]:
    frames = []
    for index in range(count):
        phase = 2.0 * math.pi * index / count
        frames.append(render_orb_base(size, phase))
    return frames


def _resize_orb_frame(frame: Any, size: int, resample: Any) -> Any:
    import numpy as np
    from PIL import Image

    source = np.asarray(frame)
    rgb = source[..., :3].copy()
    rgb[source[..., 3] == 0] = HALO_BACKGROUND
    rgb = np.asarray(
        Image.fromarray(rgb, "RGB").resize((size, size), resample)
    )
    alpha = np.asarray(
        Image.fromarray(source[..., 3], "L").resize((size, size), resample)
    )
    pixels = np.dstack([rgb, alpha])
    pixels[alpha == 0, :3] = TRANSPARENT_RGB
    return Image.fromarray(pixels, "RGBA")


def _play_listen_sound() -> None:
    if os.name != "nt":
        return
    handle = tempfile.NamedTemporaryFile(
        suffix=".wav", prefix="akki-listen-", delete=False
    )
    try:
        handle.write(listen_sound_wav())
        handle.close()
        import winsound

        winsound.PlaySound(
            handle.name, winsound.SND_FILENAME | winsound.SND_NODEFAULT
        )
    except Exception:
        pass
    finally:
        try:
            handle.close()
        except Exception:
            pass
        try:
            os.unlink(handle.name)
        except OSError:
            pass


class ListeningIndicator:
    def __init__(self, enabled: Callable[[], bool] | None = None) -> None:
        self._enabled = enabled or (lambda: True)
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._root: object | None = None
        self._canvas: object | None = None
        self._visible = False
        self._frames: list[object] = []
        self._frame_index = 0
        self._image_id: object | None = None
        self._pil_frames: list[Any] | None = None
        self._frames_ready = threading.Event()
        self._warm_thread: threading.Thread | None = None

    def warm_up(self) -> None:
        if self._pil_frames is not None:
            return
        if self._warm_thread is not None and self._warm_thread.is_alive():
            return
        self._warm_thread = threading.Thread(
            target=self._prepare_frames, name="akki-orb-warmup", daemon=True
        )
        self._warm_thread.start()

    def _prepare_frames(self) -> None:
        try:
            self._pil_frames = build_orb_frames()
        except Exception:
            self._pil_frames = []
        finally:
            self._frames_ready.set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name="akki-listening-bubble", daemon=True
        )
        self._thread.start()

    def show(self, text: str = "listening", *, sound: bool = True) -> None:
        if not self._enabled():
            return
        if sound:
            _play_listen_sound()
        self.start()
        self._queue.put(("show", text))

    def hide(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            return
        self._queue.put(("hide", ""))

    def stop(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            return
        self._queue.put(("stop", ""))

    def _run(self) -> None:
        try:
            import tkinter as tk
            from PIL import Image, ImageTk
        except ImportError as exc:
            logger.warning("listening bubble unavailable: %s", exc)
            return

        try:
            root = tk.Tk()
        except Exception:
            logger.exception("could not create listening bubble window")
            return
        logger.info("listening bubble window created")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        root.configure(bg=TRANSPARENT)
        screen_w = root.winfo_screenwidth()
        root.geometry(bubble_geometry(screen_w))
        root.update_idletasks()
        canvas = tk.Canvas(
            root,
            width=ORB_DISPLAY_SIZE,
            height=ORB_DISPLAY_SIZE,
            bg=TRANSPARENT,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack()

        resample = getattr(Image, "Resampling", Image).LANCZOS
        if self._pil_frames is None:
            self.warm_up()
        if not self._frames_ready.wait(timeout=20.0):
            logger.warning("orb frames not ready after 20s")
        pil_frames = self._pil_frames
        if not pil_frames:
            logger.error("orb frames unavailable; listening bubble disabled")
            return
        logger.info("listening bubble frames ready=%d", len(pil_frames))
        frames = [
            _resize_orb_frame(frame, ORB_DISPLAY_SIZE, resample)
            for frame in pil_frames
        ]
        self._frames = [ImageTk.PhotoImage(frame) for frame in frames]
        self._image_id = canvas.create_image(
            ORB_DISPLAY_SIZE / 2,
            ORB_DISPLAY_SIZE / 2,
            image=self._frames[0],
        )
        self._root = root
        self._canvas = canvas
        root.withdraw()
        root.after(ORB_FRAME_MS, self._poll)
        root.mainloop()

    def _poll(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            while True:
                command, _text = self._queue.get_nowait()
                if command == "show":
                    self._frame_index = 0
                    self._visible = True
                    root.deiconify()
                    root.lift()
                    root.attributes("-topmost", True)
                    logger.info("listening bubble shown")
                elif command == "hide":
                    self._visible = False
                    root.withdraw()
                elif command == "stop":
                    root.destroy()
                    self._root = None
                    return
        except queue.Empty:
            pass
        if self._visible:
            self._animate()
        root.after(ORB_FRAME_MS, self._poll)

    def _animate(self) -> None:
        canvas = self._canvas
        if canvas is None or not self._frames or self._image_id is None:
            return
        canvas.itemconfigure(
            self._image_id,
            image=self._frames[self._frame_index % len(self._frames)],
        )
        self._frame_index += 1
