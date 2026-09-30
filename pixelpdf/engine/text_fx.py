"""Animated text effects, all pure functions of time `t` (seconds).

Offsets and color functions plug straight into `draw_text`:

    draw_text(c, "hello", x, y, offsets=wave(t), colors=rainbow(t))
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from .canvas import Canvas

__all__ = ["typewriter", "wave", "bounce", "rainbow", "fade_in", "glitch", "hsv"]


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> tuple[int, int, int]:
    """HSV (all 0..1, hue wraps) to an 8-bit RGB tuple."""
    h = (h % 1.0) * 6
    i, f = int(h), h - int(h)
    p, q, u = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, u, p), (q, v, p), (p, v, u), (p, q, v), (u, p, v), (v, p, q)][i % 6]
    return round(r * 255), round(g * 255), round(b * 255)


def typewriter(text: str, t: float, cps: float = 12.0, cursor: str = "_",
               blink: float = 0.5) -> str:
    """The prefix of `text` typed after t seconds at `cps` characters/second.

    A blinking cursor (half-period `blink` seconds) follows the typed text.
    """
    shown = text[: max(0, int(t * cps))]
    if cursor and (blink <= 0 or int(t / blink) % 2 == 0):
        shown += cursor
    return shown


def wave(t: float, amplitude: float = 4.0, wavelength: float = 8.0,
         speed: float = 2.0) -> Callable[[int], tuple[float, float]]:
    """Per-character vertical sine offsets travelling along the text."""
    def offset(i: int) -> tuple[float, float]:
        return 0.0, amplitude * math.sin(2 * math.pi * (i / wavelength - speed * t))
    return offset


def bounce(t: float, height: float = 8.0, period: float = 0.6,
           stagger: float = 0.08) -> Callable[[int], tuple[float, float]]:
    """Characters hop in sequence, like a stadium wave."""
    def offset(i: int) -> tuple[float, float]:
        phase = ((t - i * stagger) / period) % 1.0
        return 0.0, -height * abs(math.sin(math.pi * phase)) ** 2
    return offset


def rainbow(t: float, speed: float = 0.25, spread: float = 0.06, saturation: float = 0.8,
            value: float = 1.0) -> Callable[[int], tuple[int, int, int]]:
    """Per-character hues cycling over time."""
    return lambda i: hsv(t * speed + i * spread, saturation, value)


def fade_in(t: float, color, background, duration: float = 0.3,
            stagger: float = 0.05) -> Callable[[int], tuple[int, ...]]:
    """Characters fade from `background` to `color` one after another."""
    fg = np.asarray(color, dtype=float)
    bg = np.asarray(background, dtype=float)

    def pick(i: int):
        k = min(max((t - i * stagger) / duration, 0.0), 1.0)
        return tuple(int(round(v)) for v in bg + (fg - bg) * k)
    return pick


def glitch(canvas: Canvas, x: int, y: int, w: int, h: int, t: float, *,
           intensity: float = 1.0, fps: float = 12.0, seed: int = 0) -> None:
    """Digital glitch on a region: shifted slices plus RGB channel split.

    The pattern changes `fps` times per second and is deterministic in
    (t, seed), so repeated renders of a frame match exactly.
    """
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, canvas.width), min(y + h, canvas.height)
    if x0 >= x1 or y0 >= y1 or intensity <= 0:
        return
    rng = np.random.default_rng([seed, int(t * fps)])
    region = canvas.pixels[y0:y1, x0:x1]
    out = region.copy()
    rows = y1 - y0
    for _ in range(rng.poisson(3 * intensity)):
        top = int(rng.integers(0, rows))
        band = int(rng.integers(1, max(2, rows // 6)))
        shift = int(rng.normal(0, 6 * intensity))
        out[top:top + band] = _shift_x(region[top:top + band], shift)
    if canvas.channels == 3:
        split = int(round(2 * intensity))
        out[:, :, 0] = _shift_x(out[:, :, 0], split)
        out[:, :, 2] = _shift_x(out[:, :, 2], -split)
    region[...] = out


def _shift_x(a: np.ndarray, shift: int) -> np.ndarray:
    """Shift columns right by `shift` (left if negative), repeating the edge column."""
    width = a.shape[1]
    cols = np.clip(np.arange(width) - shift, 0, width - 1)
    return a[:, cols]
