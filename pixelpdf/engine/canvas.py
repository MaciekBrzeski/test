"""Pixel framebuffer backed by a numpy uint8 array.

Coordinates follow screen convention: (0, 0) is the top-left pixel, x
grows right and y grows down. `canvas.pixels` is the raw (H, W, C) array
and may be written to directly for vectorised effects.
"""

from __future__ import annotations

from typing import Sequence, Union

import numpy as np

__all__ = ["Canvas", "Color", "parse_color", "a4_size", "A4_MM"]

A4_MM = (210.0, 297.0)
MM_PER_INCH = 25.4

Color = Union[int, Sequence[int], str]

_MODES = {"L": 1, "RGB": 3, "CMYK": 4}


def a4_size(dpi: float) -> tuple[int, int]:
    """Pixel dimensions (width, height) of an A4 page at `dpi`."""
    return tuple(round(mm / MM_PER_INCH * dpi) for mm in A4_MM)  # type: ignore[return-value]


def parse_color(color: Color, channels: int) -> np.ndarray:
    """Normalise a color into a length-`channels` uint8 array.

    Accepts an int (gray level, replicated across channels), a sequence
    with one value per channel, or a '#rgb' / '#rrggbb' hex string.
    """
    if isinstance(color, str):
        hexstr = color.lstrip("#")
        if len(hexstr) == 3:
            hexstr = "".join(ch * 2 for ch in hexstr)
        if len(hexstr) != 6:
            raise ValueError(f"invalid hex color {color!r}")
        rgb = [int(hexstr[i : i + 2], 16) for i in (0, 2, 4)]
        if channels == 3:
            values = rgb
        elif channels == 1:
            values = [round(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2])]
        else:
            raise ValueError("hex colors are only supported for L and RGB canvases")
    elif isinstance(color, (int, np.integer)):
        values = [int(color)] * channels if channels != 4 else [0, 0, 0, 255 - int(color)]
    else:
        values = [int(v) for v in color]
        if len(values) != channels:
            raise ValueError(f"expected {channels} color components, got {len(values)}")
    if any(v < 0 or v > 255 for v in values):
        raise ValueError(f"color components must be in 0..255, got {values}")
    return np.array(values, dtype=np.uint8)


class Canvas:
    def __init__(self, width: int, height: int, mode: str = "RGB", background: Color = 255):
        if mode not in _MODES:
            raise ValueError(f"mode must be one of {sorted(_MODES)}, got {mode!r}")
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
        self.mode = mode
        self.pixels = np.empty((height, width, _MODES[mode]), dtype=np.uint8)
        self.fill(background)

    @classmethod
    def from_array(cls, array: np.ndarray, mode: str | None = None) -> "Canvas":
        array = np.asarray(array)
        if array.ndim == 2:
            array = array[:, :, np.newaxis]
        if mode is None:
            mode = {1: "L", 3: "RGB", 4: "CMYK"}[array.shape[2]]
        canvas = cls.__new__(cls)
        canvas.mode = mode
        canvas.pixels = np.ascontiguousarray(array, dtype=np.uint8)
        if canvas.pixels.shape[2] != _MODES[mode]:
            raise ValueError(f"array has {array.shape[2]} channels, mode {mode} needs {_MODES[mode]}")
        return canvas

    @property
    def width(self) -> int:
        return self.pixels.shape[1]

    @property
    def height(self) -> int:
        return self.pixels.shape[0]

    @property
    def channels(self) -> int:
        return self.pixels.shape[2]

    def color(self, color: Color) -> np.ndarray:
        return parse_color(color, self.channels)

    def fill(self, color: Color) -> None:
        self.pixels[:, :] = self.color(color)

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        """Set one pixel; coordinates outside the canvas are ignored."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y, x] = self.color(color)

    def get_pixel(self, x: int, y: int) -> tuple[int, ...]:
        return tuple(int(v) for v in self.pixels[y, x])

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        """Fill an axis-aligned rectangle, clipped to the canvas."""
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.width), min(y + h, self.height)
        if x0 < x1 and y0 < y1:
            self.pixels[y0:y1, x0:x1] = self.color(color)

    def copy(self) -> "Canvas":
        return Canvas.from_array(self.pixels.copy(), self.mode)
