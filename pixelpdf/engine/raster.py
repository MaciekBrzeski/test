"""Drawing primitives.

Coordinates are in pixels with integer values at pixel *centres*: a circle
at (10, 10) is centred on pixel (10, 10). Shapes are drawn from signed
distance fields evaluated over the shape's bounding box, which gives
consistent anti-aliasing (`aa=True`, coverage = 0.5 - distance) or hard,
pixel-exact edges (`aa=False`, a pixel is in when its centre is inside).

`color` may be a single color or a *paint*: a callable f(X, Y) returning an
(h, w, C) array of colors for the pixel-centre grids X, Y (see
`linear_gradient` / `radial_gradient`).
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import numpy as np

from .canvas import Canvas, _composite, _to_u8, parse_color

__all__ = [
    "fill_sdf", "line", "line_pixels", "polyline", "circle", "ellipse", "arc", "rect",
    "polygon", "linear_gradient", "radial_gradient",
]

Paint = Callable[[np.ndarray, np.ndarray], np.ndarray]


# -- core --------------------------------------------------------------------

def fill_sdf(canvas: Canvas, bbox: tuple[float, float, float, float],
             sdf: Callable[[np.ndarray, np.ndarray], np.ndarray], color, *,
             aa: bool = True, mode: str = "normal", opacity: float = 1.0) -> None:
    """Fill the region where `sdf(X, Y) <= 0`, evaluated within `bbox` = (x0, y0, x1, y1)."""
    x0 = max(math.floor(bbox[0]) - 1, 0)
    y0 = max(math.floor(bbox[1]) - 1, 0)
    x1 = min(math.ceil(bbox[2]) + 2, canvas.width)
    y1 = min(math.ceil(bbox[3]) + 2, canvas.height)
    if x0 >= x1 or y0 >= y1:
        return
    Y, X = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = sdf(X, Y)
    coverage = np.clip(0.5 - d, 0.0, 1.0) if aa else (d <= 0).astype(np.float32)
    if not coverage.any():
        return
    fill = _resolve_paint(canvas, color, X, Y)
    canvas.blend(x0, y0, coverage, fill, mode=mode, opacity=opacity)


def _resolve_paint(canvas: Canvas, color, X, Y):
    if callable(color):
        return np.asarray(color(X, Y), dtype=np.float32)
    return canvas.color(color)


# -- lines -------------------------------------------------------------------

def line_pixels(x0: int, y0: int, x1: int, y1: int) -> tuple[np.ndarray, np.ndarray]:
    """Bresenham line from (x0, y0) to (x1, y1) inclusive; returns (xs, ys)."""
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    xs, ys = [], []
    while True:
        xs.append(x0)
        ys.append(y0)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return np.array(xs), np.array(ys)


def _segment_distance(X, Y, x0, y0, x1, y1):
    vx, vy = x1 - x0, y1 - y0
    length_sq = vx * vx + vy * vy
    if length_sq == 0:
        return np.hypot(X - x0, Y - y0)
    t = np.clip(((X - x0) * vx + (Y - y0) * vy) / length_sq, 0.0, 1.0)
    return np.hypot(X - (x0 + t * vx), Y - (y0 + t * vy))


def line(canvas: Canvas, x0: float, y0: float, x1: float, y1: float, color, *,
         width: float = 1.0, aa: bool = True, mode: str = "normal",
         opacity: float = 1.0) -> None:
    """Line segment with round caps. `aa=False, width=1` draws a Bresenham line."""
    if not aa and width <= 1:
        xs, ys = line_pixels(x0, y0, x1, y1)
        inside = (xs >= 0) & (xs < canvas.width) & (ys >= 0) & (ys < canvas.height)
        xs, ys = xs[inside], ys[inside]
        if callable(color):
            fill = _resolve_paint(canvas, color, xs.astype(np.float32)[None], ys.astype(np.float32)[None])[0]
        else:
            fill = canvas.color(color).astype(np.float32)
        dst = canvas.pixels[ys, xs].astype(np.float32)
        canvas.pixels[ys, xs] = _to_u8(_composite(dst, fill, np.float32(opacity), mode))
        return
    half = width / 2
    bbox = (min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half)
    fill_sdf(canvas, bbox, lambda X, Y: _segment_distance(X, Y, x0, y0, x1, y1) - half,
             color, aa=aa, mode=mode, opacity=opacity)


def polyline(canvas: Canvas, points: Sequence[tuple[float, float]], color, *,
             width: float = 1.0, closed: bool = False, aa: bool = True,
             mode: str = "normal", opacity: float = 1.0) -> None:
    """Connected segments drawn as one shape (joints are not double-blended)."""
    pts = [(float(x), float(y)) for x, y in points]
    if closed:
        pts.append(pts[0])
    if len(pts) < 2:
        return
    half = width / 2
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    segments = list(zip(pts, pts[1:]))

    def sdf(X, Y):
        d = np.full(X.shape, np.inf, dtype=np.float32)
        for (ax, ay), (bx, by) in segments:
            d = np.minimum(d, _segment_distance(X, Y, ax, ay, bx, by))
        return d - half

    fill_sdf(canvas, (min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half),
             sdf, color, aa=aa, mode=mode, opacity=opacity)


# -- curves ------------------------------------------------------------------

def circle(canvas: Canvas, cx: float, cy: float, r: float, color, *,
           fill: bool = True, width: float = 1.0, aa: bool = True,
           mode: str = "normal", opacity: float = 1.0) -> None:
    """Filled disc, or a ring of the given stroke `width` when fill=False."""
    reach = r + (0 if fill else width / 2)
    if fill:
        def sdf(X, Y):
            return np.hypot(X - cx, Y - cy) - r
    else:
        def sdf(X, Y):
            return np.abs(np.hypot(X - cx, Y - cy) - r) - width / 2
    fill_sdf(canvas, (cx - reach, cy - reach, cx + reach, cy + reach), sdf, color,
             aa=aa, mode=mode, opacity=opacity)


def ellipse(canvas: Canvas, cx: float, cy: float, rx: float, ry: float, color, *,
            aa: bool = True, mode: str = "normal", opacity: float = 1.0) -> None:
    """Filled axis-aligned ellipse (distance is approximate near the tips)."""
    k = min(rx, ry)

    def sdf(X, Y):
        return (np.hypot((X - cx) / rx, (Y - cy) / ry) - 1.0) * k

    fill_sdf(canvas, (cx - rx, cy - ry, cx + rx, cy + ry), sdf, color,
             aa=aa, mode=mode, opacity=opacity)


def arc(canvas: Canvas, cx: float, cy: float, r: float, start: float, end: float, color, *,
        width: float = 1.0, aa: bool = True, mode: str = "normal", opacity: float = 1.0) -> None:
    """Stroked circular arc with round caps.

    Angles are in radians, measured clockwise on screen from the +x axis
    (y points down), sweeping from `start` to `end`. A sweep of 2π or more
    draws the full ring.
    """
    sweep = end - start
    if sweep < 0:
        start, sweep = end, -sweep
    half = width / 2
    reach = r + half
    if sweep >= 2 * math.pi:
        circle(canvas, cx, cy, r, color, fill=False, width=width, aa=aa, mode=mode, opacity=opacity)
        return
    ex0, ey0 = cx + r * math.cos(start), cy + r * math.sin(start)
    ex1, ey1 = cx + r * math.cos(start + sweep), cy + r * math.sin(start + sweep)

    def sdf(X, Y):
        dx, dy = X - cx, Y - cy
        rel = np.mod(np.arctan2(dy, dx) - start, 2 * math.pi)
        on_arc = rel <= sweep
        ring = np.abs(np.hypot(dx, dy) - r)
        caps = np.minimum(np.hypot(X - ex0, Y - ey0), np.hypot(X - ex1, Y - ey1))
        return np.where(on_arc, ring, caps) - half

    fill_sdf(canvas, (cx - reach, cy - reach, cx + reach, cy + reach), sdf, color,
             aa=aa, mode=mode, opacity=opacity)


# -- areas -------------------------------------------------------------------

def rect(canvas: Canvas, x: float, y: float, w: float, h: float, color, *,
         radius: float = 0.0, fill: bool = True, width: float = 1.0, aa: bool = True,
         mode: str = "normal", opacity: float = 1.0) -> None:
    """Rectangle covering pixels x..x+w-1, y..y+h-1, optionally with rounded corners.

    With integer arguments and radius=0 a filled rect covers exactly those
    pixels at full coverage, with or without anti-aliasing.
    """
    cx, cy = x + (w - 1) / 2, y + (h - 1) / 2
    hx, hy = w / 2, h / 2
    radius = min(radius, hx, hy)

    def box(X, Y):
        qx = np.abs(X - cx) - (hx - radius)
        qy = np.abs(Y - cy) - (hy - radius)
        outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
        inside = np.minimum(np.maximum(qx, qy), 0)
        return outside + inside - radius

    if fill:
        sdf = box
    else:
        def sdf(X, Y):
            return np.abs(box(X, Y) + width / 2) - width / 2
    fill_sdf(canvas, (x - 1, y - 1, x + w, y + h), sdf, color, aa=aa, mode=mode, opacity=opacity)


def polygon(canvas: Canvas, points: Iterable[tuple[float, float]], color, *,
            aa: bool = True, mode: str = "normal", opacity: float = 1.0) -> None:
    """Filled polygon (even-odd rule), with anti-aliased edges."""
    pts = np.asarray(list(points), dtype=np.float32)
    if len(pts) < 3:
        return
    edges = list(zip(pts, np.roll(pts, -1, axis=0)))

    def sdf(X, Y):
        dist = np.full(X.shape, np.inf, dtype=np.float32)
        inside = np.zeros(X.shape, dtype=bool)
        for (ax, ay), (bx, by) in edges:
            dist = np.minimum(dist, _segment_distance(X, Y, ax, ay, bx, by))
            crosses = (ay > Y) != (by > Y)
            with np.errstate(divide="ignore", invalid="ignore"):
                x_at = ax + (Y - ay) * (bx - ax) / (by - ay)
            inside ^= crosses & (X < x_at)
        return np.where(inside, -dist, dist)

    fill_sdf(canvas, (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()),
             sdf, color, aa=aa, mode=mode, opacity=opacity)


# -- paints ------------------------------------------------------------------

def _stops(stops, channels: int):
    stops = sorted(stops, key=lambda s: s[0])
    positions = np.array([s[0] for s in stops], dtype=np.float32)
    colors = np.stack([parse_color(s[1], channels).astype(np.float32) for s in stops])
    return positions, colors


def _sample_stops(t: np.ndarray, positions: np.ndarray, colors: np.ndarray) -> np.ndarray:
    return np.stack([np.interp(t, positions, colors[:, c]) for c in range(colors.shape[1])],
                    axis=-1).astype(np.float32)


def linear_gradient(x0: float, y0: float, x1: float, y1: float, stops, channels: int = 3) -> Paint:
    """Paint varying along the line (x0, y0) -> (x1, y1); stops = [(0..1, color), ...]."""
    positions, colors = _stops(stops, channels)
    vx, vy = x1 - x0, y1 - y0
    length_sq = vx * vx + vy * vy or 1.0

    def paint(X, Y):
        return _sample_stops(((X - x0) * vx + (Y - y0) * vy) / length_sq, positions, colors)

    return paint


def radial_gradient(cx: float, cy: float, r: float, stops, channels: int = 3) -> Paint:
    """Paint varying with distance from (cx, cy); t = 1 at radius r."""
    positions, colors = _stops(stops, channels)

    def paint(X, Y):
        return _sample_stops(np.hypot(X - cx, Y - cy) / r, positions, colors)

    return paint
