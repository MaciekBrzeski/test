"""Loading spinners, each a pure function of time `t` (seconds).

Every spinner draws centred on (cx, cy) within radius `r`, and repeats
with its `period`, so `period * fps` frames make a seamless loop.
"""

from __future__ import annotations

import math

from . import raster
from .canvas import Canvas

__all__ = ["arc_spinner", "dots_spinner", "bars_spinner", "pulse_spinner", "orbit_spinner"]


def _mix(canvas: Canvas, color, background, k: float):
    fg = canvas.color(color).astype(float)
    bg = canvas.color(background).astype(float)
    return tuple(int(round(v)) for v in bg + (fg - bg) * k)


def arc_spinner(canvas: Canvas, cx: float, cy: float, r: float, t: float, color, *,
                width: float | None = None, period: float = 1.5, track=None) -> None:
    """Material-style arc that grows and shrinks while rotating."""
    width = width or max(2.0, r / 5)
    if track is not None:
        raster.circle(canvas, cx, cy, r, track, fill=False, width=width)
    phase = (t / period) % 1.0
    # Head leads during the first half, tail catches up in the second.
    head = 0.75 * (1 - (1 - min(phase * 2, 1)) ** 3)
    tail = 0.75 * max(phase * 2 - 1, 0) ** 3 if phase > 0.5 else 0.0
    spin = 2 * math.pi * (phase + t / (period * 2.5))
    start = spin + 2 * math.pi * (tail + 0.75 * phase)
    end = spin + 2 * math.pi * (head + 0.75 * phase) + 0.15
    raster.arc(canvas, cx, cy, r, start, end, color, width=width)


def dots_spinner(canvas: Canvas, cx: float, cy: float, r: float, t: float, color, *,
                 count: int = 8, period: float = 1.0, background=255) -> None:
    """Ring of dots with a bright head fading around the circle."""
    dot = r / 5
    head = (t / period) % 1.0 * count
    for i in range(count):
        a = 2 * math.pi * i / count - math.pi / 2
        age = (head - i) % count / count  # 0 = brightest
        k = max(0.15, 1 - age)
        raster.circle(canvas, cx + (r - dot) * math.cos(a), cy + (r - dot) * math.sin(a),
                      dot * (0.6 + 0.4 * k), _mix(canvas, color, background, k))


def bars_spinner(canvas: Canvas, cx: float, cy: float, r: float, t: float, color, *,
                 count: int = 12, period: float = 1.0, background=255) -> None:
    """iOS-style radial bars."""
    head = (t / period) % 1.0 * count
    for i in range(count):
        a = 2 * math.pi * i / count - math.pi / 2
        age = (head - i) % count / count
        k = max(0.15, 1 - age)
        c, s = math.cos(a), math.sin(a)
        raster.line(canvas, cx + c * r * 0.45, cy + s * r * 0.45, cx + c * r * 0.95,
                    cy + s * r * 0.95, _mix(canvas, color, background, k), width=r / 7)


def pulse_spinner(canvas: Canvas, cx: float, cy: float, r: float, t: float, color, *,
                  rings: int = 3, period: float = 1.8, background=255) -> None:
    """Concentric rings expanding and fading out."""
    for i in range(rings):
        phase = (t / period + i / rings) % 1.0
        raster.circle(canvas, cx, cy, r * phase, _mix(canvas, color, background, 1 - phase),
                      fill=False, width=max(1.5, r / 12))


def orbit_spinner(canvas: Canvas, cx: float, cy: float, r: float, t: float, color, *,
                  period: float = 1.2, trail: int = 10, background=255) -> None:
    """A dot orbiting on an ellipse, with a fading trail."""
    for i in range(trail, -1, -1):
        a = 2 * math.pi * ((t - i * period / 40) / period)
        k = 1 - i / (trail + 1)
        raster.circle(canvas, cx + r * 0.85 * math.cos(a), cy + r * 0.45 * math.sin(a),
                      r / 7 * (0.4 + 0.6 * k), _mix(canvas, color, background, k))
    raster.circle(canvas, cx, cy, r / 5, color)
    # Redraw the front half of the orbit over the centre dot for depth.
    if math.sin(2 * math.pi * t / period) > 0:
        a = 2 * math.pi * t / period
        raster.circle(canvas, cx + r * 0.85 * math.cos(a), cy + r * 0.45 * math.sin(a), r / 7, color)
