import math
import zlib

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.engine import spinners
from pixelpdf.engine.anim import (EASINGS, Keyframes, contact_sheet, ease, frame_times,
                                  render_frames, save_frames)
from pixelpdf.engine.png import encode_png


@pytest.mark.parametrize("name", sorted(EASINGS))
def test_easing_endpoints(name):
    assert ease(name, 0) == pytest.approx(0, abs=1e-9)
    assert ease(name, 1) == pytest.approx(1, abs=1e-9)
    assert ease(name, -1) == ease(name, 0) and ease(name, 2) == ease(name, 1)


def test_unknown_easing():
    with pytest.raises(ValueError):
        ease("nope", 0.5)


def test_keyframes():
    k = Keyframes([(0, 0), (1, 10), (2, 10), (3, 0, "in_quad")])
    assert [k(-1), k(0), k(0.5), k(1.5), k(2.5), k(9)] == pytest.approx([0, 0, 5, 10, 7.5, 0])


def test_keyframes_tuples_and_loop():
    k = Keyframes([(0, (0, 0)), (2, (10, 20))], loop=2)
    assert k(1) == pytest.approx((5, 10))
    assert k(3) == pytest.approx((5, 10))


def test_frame_times():
    assert frame_times(1, 4) == [0, 0.25, 0.5, 0.75]
    assert len(frame_times(1.5, 24)) == 36


def test_render_frames_passes_time():
    seen = []
    frames = list(render_frames(lambda c, t: seen.append(t), 4, 3, duration=0.5, fps=4))
    assert seen == [0, 0.25]
    assert all(f.pixels.shape == (3, 4, 3) for f in frames)


def test_contact_sheet_layout():
    frames = [Canvas(2, 2, background=v) for v in (10, 20, 30)]
    sheet = contact_sheet(frames, columns=2, gap=1, background=0)
    assert (sheet.width, sheet.height) == (7, 7)
    assert sheet.get_pixel(1, 1)[0] == 10
    assert sheet.get_pixel(4, 1)[0] == 20
    assert sheet.get_pixel(1, 4)[0] == 30
    assert sheet.get_pixel(4, 4)[0] == 0


def _decode_png(data: bytes) -> np.ndarray:
    PIL = pytest.importorskip("PIL.Image")
    import io
    return np.asarray(PIL.open(io.BytesIO(data)))


@pytest.mark.parametrize("shape", [(5, 7, 3), (9, 4), (300, 3, 3)])
def test_png_roundtrip(rng, shape):
    pixels = rng.integers(0, 256, shape, dtype=np.uint8)
    np.testing.assert_array_equal(_decode_png(encode_png(pixels)), pixels)


def test_png_rejects_empty():
    with pytest.raises(ValueError):
        encode_png(np.zeros((0, 5, 3), np.uint8))


def test_save_frames(tmp_path):
    paths = save_frames([Canvas(3, 3), Canvas(3, 3)], tmp_path / "f")
    assert [p.name for p in paths] == ["frame_0000.png", "frame_0001.png"]
    assert paths[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("name", spinners.__all__)
def test_spinners_draw_and_loop(name):
    fn = getattr(spinners, name)

    def frame(t):
        c = Canvas(60, 60, background=255)
        fn(c, 30, 30, 25, t, "#3366ff")
        return c.pixels

    first = frame(0.0)
    assert (first != 255).any()
    period = {"arc_spinner": 1.5, "pulse_spinner": 1.8, "orbit_spinner": 1.2}.get(name, 1.0)
    later = frame(period * (5 if name == "arc_spinner" else 1))
    np.testing.assert_allclose(first.astype(int), later.astype(int), atol=2)
    assert not np.array_equal(frame(0.0), frame(period / 4))
