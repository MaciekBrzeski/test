import numpy as np
import pytest

from pixelpdf import Canvas, a4_size, parse_color


def test_a4_size():
    assert a4_size(72) == (595, 842)
    assert a4_size(144) == (1191, 1684)
    assert a4_size(288) == (2381, 3368)


@pytest.mark.parametrize("color, channels, expected", [
    (0, 3, [0, 0, 0]),
    (200, 1, [200]),
    ((1, 2, 3), 3, [1, 2, 3]),
    ("#ff8000", 3, [255, 128, 0]),
    ("#f80", 3, [255, 136, 0]),
    ("#ffffff", 1, [255]),
    (255, 4, [0, 0, 0, 0]),
    (0, 4, [0, 0, 0, 255]),
])
def test_parse_color(color, channels, expected):
    assert parse_color(color, channels).tolist() == expected


@pytest.mark.parametrize("color, channels", [((1, 2), 3), (300, 3), ("#12345", 3), ("#fff", 4)])
def test_parse_color_rejects(color, channels):
    with pytest.raises(ValueError):
        parse_color(color, channels)


def test_background_and_pixels():
    c = Canvas(4, 3, background="#102030")
    assert (c.width, c.height, c.channels) == (4, 3, 3)
    assert c.get_pixel(3, 2) == (16, 32, 48)
    c.set_pixel(1, 2, (9, 8, 7))
    assert c.get_pixel(1, 2) == (9, 8, 7)
    assert c.pixels[2, 1].tolist() == [9, 8, 7]  # row-major: pixels[y, x]


def test_set_pixel_out_of_bounds_is_ignored():
    c = Canvas(2, 2, background=0)
    for x, y in [(-1, 0), (0, -1), (2, 0), (0, 2)]:
        c.set_pixel(x, y, 255)
    assert not c.pixels.any()


def test_fill_rect_clips():
    c = Canvas(5, 5, mode="L", background=0)
    c.fill_rect(3, -2, 10, 4, 255)
    expected = np.zeros((5, 5), dtype=np.uint8)
    expected[0:2, 3:5] = 255
    np.testing.assert_array_equal(c.pixels[:, :, 0], expected)


def test_from_array_and_copy():
    arr = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    c = Canvas.from_array(arr)
    assert c.mode == "RGB"
    d = c.copy()
    d.set_pixel(0, 0, 0)
    assert c.get_pixel(0, 0) == (0, 1, 2)
    assert Canvas.from_array(np.zeros((2, 2))).mode == "L"


def test_invalid_canvas():
    with pytest.raises(ValueError):
        Canvas(0, 5)
    with pytest.raises(ValueError):
        Canvas(5, 5, mode="RGBA")


def test_upscale():
    c = Canvas(2, 1, background=0)
    c.set_pixel(1, 0, 255)
    big = c.upscale(3)
    assert (big.width, big.height) == (6, 3)
    assert big.pixels[:, :3].max() == 0 and big.pixels[:, 3:].min() == 255
    with pytest.raises(ValueError):
        c.upscale(0)
