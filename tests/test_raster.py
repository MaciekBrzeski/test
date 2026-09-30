import math

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.engine import raster as R
from pixelpdf.engine.raster import line_pixels


def ink(c: Canvas) -> np.ndarray:
    """Coverage (0..1) of white ink on a black canvas."""
    return c.pixels[:, :, 0].astype(float) / 255


@pytest.fixture
def canvas():
    return Canvas(64, 48, background=0)


@pytest.mark.parametrize("aa", [True, False])
def test_rect_covers_exact_pixels(canvas, aa):
    R.rect(canvas, 5, 7, 10, 8, 255, aa=aa)
    expected = np.zeros((48, 64))
    expected[7:15, 5:15] = 1
    np.testing.assert_array_equal(ink(canvas), expected)


def test_rect_outline(canvas):
    R.rect(canvas, 5, 5, 10, 8, 255, fill=False, aa=False)
    expected = np.zeros((48, 64), bool)
    expected[5:13, 5:15] = True
    expected[6:12, 6:14] = False
    np.testing.assert_array_equal(ink(canvas) > 0, expected)


def test_rounded_rect_area(canvas):
    R.rect(canvas, 5, 5, 20, 16, 255, radius=5)
    assert ink(canvas).sum() == pytest.approx(20 * 16 - (4 - math.pi) * 25, abs=1.0)


@pytest.mark.parametrize("r", [3, 7.5, 15])
def test_circle_area_matches(canvas, r):
    R.circle(canvas, 32, 24, r, 255)
    assert ink(canvas).sum() == pytest.approx(math.pi * r * r, rel=0.02, abs=1.5)


def test_circle_hard_edge_is_binary(canvas):
    R.circle(canvas, 32, 24, 10, 255, aa=False)
    assert set(np.unique(canvas.pixels)) <= {0, 255}
    assert canvas.get_pixel(32, 24) == (255, 255, 255)
    assert canvas.get_pixel(32 + 11, 24) == (0, 0, 0)


def test_ring_area(canvas):
    R.circle(canvas, 32, 24, 12, 255, fill=False, width=2)
    assert ink(canvas).sum() == pytest.approx(2 * math.pi * 12 * 2, rel=0.03)


def test_arc_half_ring_area(canvas):
    R.arc(canvas, 32, 24, 12, 0, math.pi, 255, width=2)
    # Half a ring plus two round caps (two half-discs of radius 1).
    assert ink(canvas).sum() == pytest.approx(math.pi * 12 * 2 + math.pi, rel=0.03)
    assert ink(canvas)[24 + 12, 32] > 0.9    # bottom (y down, angle pi/2)
    assert ink(canvas)[24 - 12, 32] == 0     # top is not drawn


def test_bresenham_endpoints_and_continuity():
    xs, ys = line_pixels(2, 3, 17, 9)
    assert (xs[0], ys[0], xs[-1], ys[-1]) == (2, 3, 17, 9)
    steps = np.abs(np.diff(xs)) + np.abs(np.diff(ys))
    assert steps.min() >= 1 and np.abs(np.diff(xs)).max() <= 1 and np.abs(np.diff(ys)).max() <= 1
    assert len(xs) == 16  # one pixel per column on an x-major line


def test_hard_line_draws_bresenham_pixels(canvas):
    R.line(canvas, 0, 0, 63, 47, 255, aa=False)
    xs, ys = line_pixels(0, 0, 63, 47)
    expected = np.zeros((48, 64))
    expected[ys, xs] = 1
    np.testing.assert_array_equal(ink(canvas), expected)


def test_aa_line_area(canvas):
    R.line(canvas, 10, 20, 50, 20, 255, width=3)
    # 40 px long, 3 px wide, plus round caps.
    assert ink(canvas).sum() == pytest.approx(40 * 3 + math.pi * 1.5 ** 2, rel=0.03)


def test_polygon_square_is_exact(canvas):
    R.polygon(canvas, [(4.5, 4.5), (14.5, 4.5), (14.5, 14.5), (4.5, 14.5)], 255)
    expected = np.zeros((48, 64))
    expected[5:15, 5:15] = 1
    np.testing.assert_allclose(ink(canvas), expected, atol=1 / 255)


def test_polygon_triangle_area(canvas):
    R.polygon(canvas, [(5, 5), (45, 5), (5, 35)], 255)
    assert ink(canvas).sum() == pytest.approx(0.5 * 40 * 30, rel=0.02)


def test_polyline_joints_not_double_blended(canvas):
    R.polyline(canvas, [(5, 5), (30, 5), (30, 30)], 255, width=3, opacity=0.5)
    assert ink(canvas).max() <= 0.5 + 1 / 255


def test_shapes_clip_to_canvas(canvas):
    R.circle(canvas, -5, -5, 20, 255)
    R.rect(canvas, 50, 40, 100, 100, 255)
    R.line(canvas, -100, 10, 200, 10, 255, aa=False)
    R.polygon(canvas, [(-50, -50), (-10, -50), (-10, -10)], 255)
    R.circle(canvas, 1000, 1000, 5, 255)
    assert canvas.pixels.shape == (48, 64, 3)


def test_opacity_and_modes(canvas):
    canvas.fill(100)
    R.rect(canvas, 0, 0, 4, 4, 200, opacity=0.5)
    assert canvas.get_pixel(0, 0) == (150, 150, 150)
    R.rect(canvas, 4, 0, 4, 4, 200, mode="add")
    assert canvas.get_pixel(4, 0) == (255, 255, 255)
    R.rect(canvas, 8, 0, 4, 4, 128, mode="multiply")
    assert canvas.get_pixel(8, 0) == (50, 50, 50)


def test_linear_gradient_paint():
    c = Canvas(11, 1, background=0)
    R.rect(c, 0, 0, 11, 1, R.linear_gradient(0, 0, 10, 0, [(0, "#000000"), (1, "#ffffff")]))
    assert [c.get_pixel(x, 0)[0] for x in (0, 5, 10)] == [0, 128, 255]


def test_radial_gradient_paint():
    c = Canvas(21, 21, background=0)
    R.rect(c, 0, 0, 21, 21, R.radial_gradient(10, 10, 10, [(0, (255, 0, 0)), (1, (0, 0, 255))]))
    assert c.get_pixel(10, 10) == (255, 0, 0)
    assert c.get_pixel(20, 10) == (0, 0, 255)
