import string

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.engine import text_fx as fx
from pixelpdf.engine.font import DEFAULT_FONT, draw_text, measure_text


def test_every_printable_ascii_has_a_glyph():
    for ch in string.printable[:95]:
        assert DEFAULT_FONT.has_glyph(ch), ch
        if ch != " ":
            assert DEFAULT_FONT.glyph(ch).any(), ch


def test_unknown_character_draws_box():
    assert not DEFAULT_FONT.has_glyph("☃")
    assert DEFAULT_FONT.glyph("☃").sum() > 0


def test_measure():
    assert measure_text("A") == (5, 9)
    assert measure_text("AB") == (11, 9)
    assert measure_text("AB", scale=2) == (22, 18)
    assert measure_text("A\nB") == (5, 9 + 11)


def test_glyph_pixels_are_exact():
    c = Canvas(20, 12, mode="L", background=0)
    draw_text(c, "A", 2, 1, 255)
    np.testing.assert_array_equal(c.pixels[1:10, 2:7, 0] > 0, DEFAULT_FONT.glyph("A"))
    assert c.pixels.sum() == DEFAULT_FONT.glyph("A").sum() * 255


def test_scaled_text_is_crisp():
    c = Canvas(40, 30, background=0)
    draw_text(c, "Hi", 0, 0, (255, 255, 255), scale=3)
    assert set(np.unique(c.pixels)) == {0, 255}
    mask = DEFAULT_FONT.glyph("H").repeat(3, 0).repeat(3, 1)
    np.testing.assert_array_equal(c.pixels[:27, :15, 0] > 0, mask)


@pytest.mark.parametrize("align, left", [("left", 30), ("center", 30 - 5), ("right", 30 - 11)])
def test_alignment(align, left):
    c = Canvas(60, 10, mode="L", background=0)
    draw_text(c, "AB", 30, 0, 255, align=align)
    cols = np.nonzero(c.pixels[:, :, 0].any(axis=0))[0]
    assert cols.min() == left


def test_per_character_offsets_and_colors():
    c = Canvas(30, 20, background=0)
    draw_text(c, "II", 0, 5, offsets=[(0, 0), (0, -3)], colors=["#ff0000", "#0000ff"])
    red = np.nonzero((c.pixels == [255, 0, 0]).all(axis=2))
    blue = np.nonzero((c.pixels == [0, 0, 255]).all(axis=2))
    assert red[0].min() == 5 and blue[0].min() == 2


def test_typewriter():
    assert fx.typewriter("hello", 0.0, cps=10, cursor="") == ""
    assert fx.typewriter("hello", 0.25, cps=10, cursor="") == "he"
    assert fx.typewriter("hello", 5.0, cps=10, cursor="") == "hello"
    assert fx.typewriter("hi", 0.1, cps=10, cursor="_", blink=0.5) == "h_"
    assert fx.typewriter("hi", 0.6, cps=10, cursor="_", blink=0.5) == "hi"


def test_wave_and_bounce_are_periodic():
    w = fx.wave(0.0, amplitude=4, wavelength=8, speed=1)
    assert w(0)[1] == pytest.approx(0)
    assert w(2)[1] == pytest.approx(4)
    assert fx.wave(1.0, speed=1)(3)[1] == pytest.approx(fx.wave(0.0, speed=1)(3)[1])
    assert fx.bounce(0.0)(0)[1] == pytest.approx(0)
    assert fx.bounce(0.3, height=8, period=0.6)(0)[1] == pytest.approx(-8)


def test_hsv_and_rainbow():
    assert fx.hsv(0) == (255, 0, 0)
    assert fx.hsv(1 / 3) == (0, 255, 0)
    assert fx.hsv(1.0) == (255, 0, 0)
    assert fx.rainbow(0.0, spread=0.5, saturation=1)(1) == (0, 255, 255)


def test_fade_in():
    f = fx.fade_in(0.15, (255, 255, 255), (0, 0, 0), duration=0.3, stagger=0.1)
    assert f(0) == (128, 128, 128)
    assert f(5) == (0, 0, 0)


def test_glitch_is_deterministic_and_local():
    def render(t, glitch=True):
        c = Canvas(120, 30, background=255)
        draw_text(c, "GLITCH", 5, 5, 0, scale=2)
        if glitch:
            fx.glitch(c, 0, 0, 40, 30, t, intensity=2, seed=7)
        return c.pixels

    a, b = render(0.5), render(0.5)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, render(0.5, glitch=False))
    np.testing.assert_array_equal(a[:, 40:], render(0.5, glitch=False)[:, 40:])
