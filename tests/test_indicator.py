import io
import math
import unittest
import wave
from unittest import mock

from akki import indicator


class IndicatorTests(unittest.TestCase):
    def test_listen_sound_is_valid_pcm_wav(self) -> None:
        data = indicator.listen_sound_wav()
        self.assertTrue(data.startswith(b"RIFF"))
        self.assertIn(b"WAVE", data[:16])
        with wave.open(io.BytesIO(data), "rb") as handle:
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getsampwidth(), 2)
            self.assertEqual(handle.getframerate(), 22050)
            self.assertGreater(handle.getnframes(), 0)

    def test_bubble_geometry_sits_in_top_right(self) -> None:
        self.assertEqual(
            indicator.bubble_geometry(1920),
            f"{indicator.ORB_DISPLAY_SIZE}x{indicator.ORB_DISPLAY_SIZE}"
            f"+{1920 - indicator.ORB_DISPLAY_SIZE - indicator.BUBBLE_MARGIN}"
            f"+{indicator.BUBBLE_TOP}",
        )
        self.assertTrue(indicator.bubble_geometry(80).endswith("+0+24"))

    def test_halo_frames_show_a_translucent_energy_entity(self) -> None:
        frames = indicator.build_orb_frames(size=64, count=3)
        self.assertEqual(len(frames), 3)
        first = frames[0]
        self.assertEqual(first.size, (64, 64))
        self.assertEqual(first.mode, "RGBA")
        self.assertEqual(
            first.getpixel((0, 0)),
            (*indicator.TRANSPARENT_RGB, 0),
        )
        self.assertFalse(
            any(
                first.getpixel((x, y))[:3] == (0, 0, 0)
                for x in range(first.width)
                for y in range(first.height)
            )
        )
        self.assertLess(first.getpixel((32, 32))[3], 230)
        self.assertLess(
            sum(
                first.getpixel((x, y))[3] > 240
                for x in range(first.width)
                for y in range(first.height)
            ),
            first.width * first.height // 3,
        )
        self.assertGreater(first.getchannel("B").getextrema()[1], 200)
        self.assertNotEqual(first.tobytes(), frames[1].tobytes())

    def test_halo_has_cyan_ridges_and_violet_accents(self) -> None:
        frame = indicator.render_orb_base(64, 0.4)
        cyan_count = 0
        violet_count = 0
        for y in range(frame.height):
            for x in range(frame.width):
                red, green, blue, alpha = frame.getpixel((x, y))
                if alpha <= 40:
                    continue
                if green > 170 and blue > 205 and green > red + 50:
                    cyan_count += 1
                if red > green + 15 and blue > green + 25:
                    violet_count += 1
        self.assertGreater(cyan_count, 0)
        self.assertGreater(violet_count, 0)

    def test_halo_animation_wraps_without_a_seam(self) -> None:
        start = indicator.render_orb_base(64, 0.0)
        end = indicator.render_orb_base(64, 2.0 * 3.141592653589793)
        self.assertEqual(start.tobytes(), end.tobytes())

    def test_halo_frame_sequence_has_a_smooth_loop_boundary(self) -> None:
        frames = indicator.build_orb_frames(size=32)
        frame_bytes = [frame.tobytes() for frame in frames]
        adjacent_diffs = [
            sum(abs(left - right) for left, right in zip(first, second))
            for first, second in zip(frame_bytes, frame_bytes[1:])
        ]
        boundary_diff = sum(
            abs(left - right)
            for left, right in zip(frame_bytes[-1], frame_bytes[0])
        )
        self.assertLessEqual(boundary_diff, max(adjacent_diffs) * 1.6)

    def test_halo_silhouette_changes_without_clipping(self) -> None:
        frames = indicator.build_orb_frames(
            size=64, count=indicator.ORB_FRAME_COUNT
        )
        silhouettes = {frame.getchannel("A").tobytes() for frame in frames}
        self.assertGreater(len(silhouettes), 1)
        for frame in frames:
            left, top, right, bottom = frame.getchannel("A").getbbox()
            self.assertGreater(left, 0)
            self.assertGreater(top, 0)
            self.assertLess(right, frame.width)
            self.assertLess(bottom, frame.height)

    def test_resized_transparent_pixels_keep_the_transparency_key(self) -> None:
        from PIL import Image

        frame = indicator.render_orb_base(128, 0.0)
        resized = indicator._resize_orb_frame(
            frame, 32, Image.Resampling.LANCZOS
        )
        self.assertEqual(resized.getpixel((0, 0)), (*indicator.TRANSPARENT_RGB, 0))

    def test_resized_translucent_edge_fades_without_a_solid_outline(self) -> None:
        from PIL import Image

        frame = indicator.render_orb_base(128, 0.0)
        resized = indicator._resize_orb_frame(
            frame, 32, Image.Resampling.LANCZOS
        )
        translucent = []
        for y in range(resized.height):
            for x in range(resized.width):
                pixel = resized.getpixel((x, y))
                if 0 < pixel[3] < 255:
                    translucent.append(pixel)
        self.assertTrue(translucent)
        self.assertGreater(len({pixel[:3] for pixel in translucent}), 1)

    def test_outer_edge_keeps_opacity_near_the_silhouette(self) -> None:
        frame = indicator.render_orb_base(128, 0.0)
        edge_alpha = [
            frame.getpixel((x, y))[3]
            for y in range(frame.height)
            for x in range(frame.width)
            if 0.7
            < math.hypot(x - 63.5, y - 63.5) / 63.5
            < 0.8
        ]
        self.assertTrue(any(0 < alpha < 255 for alpha in edge_alpha))

    def test_animation_keeps_the_image_position_fixed(self) -> None:
        listening = indicator.ListeningIndicator()
        canvas = mock.Mock()
        listening._canvas = canvas
        listening._frames = [object()] * indicator.ORB_FRAME_COUNT
        listening._image_id = "halo"

        for _ in range(indicator.ORB_FRAME_COUNT):
            listening._animate()

        canvas.coords.assert_not_called()
        self.assertEqual(canvas.itemconfigure.call_count, indicator.ORB_FRAME_COUNT)

    def test_warm_up_builds_frames_once(self) -> None:
        listening = indicator.ListeningIndicator()
        with mock.patch(
            "akki.indicator.build_orb_frames", return_value=["frame"]
        ) as build:
            listening.warm_up()
            listening._warm_thread.join(timeout=2)
            listening.warm_up()
        build.assert_called_once()
        self.assertEqual(listening._pil_frames, ["frame"])

    def test_show_plays_sound_and_starts_bubble_when_enabled(self) -> None:
        listening = indicator.ListeningIndicator(enabled=lambda: True)
        with mock.patch.object(listening, "start") as start, mock.patch(
            "akki.indicator._play_listen_sound"
        ) as play:
            listening.show()
        start.assert_called_once()
        play.assert_called_once()

    def test_show_can_skip_the_listen_sound(self) -> None:
        listening = indicator.ListeningIndicator(enabled=lambda: True)
        with mock.patch.object(listening, "start") as start, mock.patch(
            "akki.indicator._play_listen_sound"
        ) as play:
            listening.show("thinking", sound=False)
        start.assert_called_once()
        play.assert_not_called()

    def test_show_does_nothing_when_disabled(self) -> None:
        listening = indicator.ListeningIndicator(enabled=lambda: False)
        with mock.patch.object(listening, "start") as start, mock.patch(
            "akki.indicator._play_listen_sound"
        ) as play:
            listening.show()
        start.assert_not_called()
        play.assert_not_called()
