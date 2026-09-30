"""Animation timeline: easing curves, keyframe tracks and frame rendering.

An animation is a function `draw(canvas, t)` evaluated at each frame time.
Everything in the engine takes time explicitly, so a frame is fully
determined by `t`: frames can be rendered in any order, or in parallel.
Stateful simulations such as particles are the exception; step them
frame by frame in order.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Callable, Iterator, Sequence, Union

import numpy as np

from .canvas import Canvas, Color

__all__ = ["EASINGS", "ease", "lerp", "Keyframes", "frame_times", "render_frames",
           "save_frames", "contact_sheet"]


def _bounce_out(t: float) -> float:
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


EASINGS: dict[str, Callable[[float], float]] = {
    "linear": lambda t: t,
    "in_quad": lambda t: t * t,
    "out_quad": lambda t: 1 - (1 - t) ** 2,
    "in_out_quad": lambda t: 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2,
    "in_cubic": lambda t: t ** 3,
    "out_cubic": lambda t: 1 - (1 - t) ** 3,
    "in_out_cubic": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "in_out_sine": lambda t: -(math.cos(math.pi * t) - 1) / 2,
    "out_back": lambda t: 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
    "out_elastic": lambda t: t if t in (0, 1) else
        2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1,
    "out_bounce": _bounce_out,
    "step": lambda t: 1.0 if t >= 1 else 0.0,
}


def ease(name: str, t: float) -> float:
    """Apply easing curve `name` to t, clamped to 0..1."""
    try:
        fn = EASINGS[name]
    except KeyError:
        raise ValueError(f"unknown easing {name!r}; choose from {sorted(EASINGS)}") from None
    return fn(min(max(t, 0.0), 1.0))


def lerp(a, b, k: float):
    """Interpolate numbers or equal-length tuples."""
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * k for x, y in zip(a, b))
    return a + (b - a) * k


class Keyframes:
    """A value animated through (time, value[, easing]) keys.

    The easing on a key shapes the segment *arriving* at that key (default
    linear). Before the first key and after the last, the value holds.
    `loop` repeats the track with that period.

        x = Keyframes([(0, 0), (1, 100, "out_bounce"), (2, 0)], loop=2)
        x(1.5)
    """

    def __init__(self, keys: Sequence[tuple], loop: float | None = None):
        if not keys:
            raise ValueError("Keyframes needs at least one key")
        parsed = []
        for key in keys:
            t, value = key[0], key[1]
            parsed.append((float(t), value, key[2] if len(key) > 2 else "linear"))
        self.keys = sorted(parsed, key=lambda k: k[0])
        self.loop = loop

    def __call__(self, t: float):
        if self.loop:
            t = t % self.loop
        keys = self.keys
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, v0, _), (t1, v1, easing) in zip(keys, keys[1:]):
            if t <= t1:
                k = ease(easing, (t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                return lerp(v0, v1, k)
        return keys[-1][1]


def frame_times(duration: float, fps: float) -> list[float]:
    """Frame start times covering [0, duration); a looping animation won't repeat frame 0."""
    count = max(1, round(duration * fps))
    return [i / fps for i in range(count)]


Draw = Callable[[Canvas, float], None]


def render_frames(draw: Draw, width: int, height: int, *, duration: float, fps: float = 24,
                  background: Color = 255, mode: str = "RGB") -> Iterator[Canvas]:
    """Yield one fresh canvas per frame, painted by draw(canvas, t)."""
    for t in frame_times(duration, fps):
        canvas = Canvas(width, height, mode, background)
        draw(canvas, t)
        yield canvas


def save_frames(frames, directory: Union[str, os.PathLike], prefix: str = "frame") -> list[Path]:
    """Write canvases as numbered PNGs; returns the paths written."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, canvas in enumerate(frames):
        path = out / f"{prefix}_{i:04d}.png"
        canvas.save_png(path)
        paths.append(path)
    return paths


def contact_sheet(frames: Sequence[Canvas], columns: int, *, gap: int = 4,
                  background: Color = 255) -> Canvas:
    """Tile frames into a grid, left to right then top to bottom."""
    frames = list(frames)
    if not frames:
        raise ValueError("no frames")
    fw, fh = frames[0].width, frames[0].height
    rows = math.ceil(len(frames) / columns)
    sheet = Canvas(columns * fw + (columns + 1) * gap, rows * fh + (rows + 1) * gap,
                   frames[0].mode, background)
    for i, frame in enumerate(frames):
        r, c = divmod(i, columns)
        sheet.pixels[gap + r * (fh + gap): gap + r * (fh + gap) + fh,
                     gap + c * (fw + gap): gap + c * (fw + gap) + fw] = frame.pixels
    return sheet
