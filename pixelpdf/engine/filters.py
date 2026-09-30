"""Vectorised image filters on float arrays: blur, resize, smoothstep."""

from __future__ import annotations

import math

import numpy as np

__all__ = ["box_blur", "gaussian_blur", "resize_bilinear", "smoothstep"]


def smoothstep(edge0, edge1, x):
    """Hermite 0..1 ramp between edge0 and edge1 (edges may be reversed)."""
    t = np.clip((np.asarray(x, dtype=np.float32) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _box_axis(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    if r <= 0:
        return a
    a = np.moveaxis(a, axis, 0)
    n = a.shape[0]
    padded = np.concatenate([np.repeat(a[:1], r + 1, axis=0), a, np.repeat(a[-1:], r, axis=0)])
    cs = np.cumsum(padded, axis=0, dtype=np.float64)
    out = (cs[2 * r + 1 : 2 * r + 1 + n] - cs[:n]) / (2 * r + 1)
    return np.moveaxis(out.astype(np.float32), 0, axis)


def box_blur(a: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a (2r+1)x(2r+1) window with clamped edges. Works on (H, W[, C])."""
    a = np.asarray(a, dtype=np.float32)
    return _box_axis(_box_axis(a, radius, 0), radius, 1)


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Approximate Gaussian blur as three box blurs of matching variance."""
    if sigma <= 0:
        return np.asarray(a, dtype=np.float32)
    # Three passes of radius r have variance r(r+1); solve for r.
    r = max(1, round((-1 + math.sqrt(1 + 4 * sigma * sigma)) / 2))
    out = np.asarray(a, dtype=np.float32)
    for _ in range(3):
        out = box_blur(out, r)
    return out


def resize_bilinear(a: np.ndarray, height: int, width: int) -> np.ndarray:
    """Resize (H, W[, C]) with pixel-centre alignment and clamped edges."""
    a = np.asarray(a, dtype=np.float32)
    src_h, src_w = a.shape[:2]
    ys = np.clip((np.arange(height) + 0.5) * (src_h / height) - 0.5, 0, src_h - 1)
    xs = np.clip((np.arange(width) + 0.5) * (src_w / width) - 0.5, 0, src_w - 1)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    y1 = np.minimum(y0 + 1, src_h - 1)
    x1 = np.minimum(x0 + 1, src_w - 1)
    fy = (ys - y0).astype(np.float32)
    fx = (xs - x0).astype(np.float32)
    if a.ndim == 3:
        fy = fy[:, None, None]
        fx = fx[None, :, None]
    else:
        fy = fy[:, None]
        fx = fx[None, :]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bottom = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy
