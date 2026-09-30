"""2D lighting: point and spot lights, shadows, glow, bloom, vignette.

Lights are accumulated into a *light map* (H, W, 3 floats, 1.0 = unlit
albedo) that multiplies the canvas. Shadows use a polar shadow map per
light: every occluder pixel is binned by angle around the light, keeping
the nearest distance per bin, so each pixel's visibility is a single
lookup. Cost is O(pixels + occluder pixels) per light rather than ray
marching. Averaging neighbouring bins gives soft penumbrae.

Light maps are smooth, so they're computed at `scale` resolution (0.5 by
default) and upsampled bilinearly; shadow edges are still taken from the
full-resolution occluder mask.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .canvas import Canvas, Color, parse_color
from .filters import gaussian_blur, resize_bilinear, smoothstep

__all__ = ["Light", "light_map", "apply_lighting", "tonemap", "glow", "bloom", "vignette"]


@dataclass
class Light:
    x: float
    y: float
    color: Color = (255, 255, 255)
    radius: float = 400.0
    intensity: float = 1.0
    direction: Optional[float] = None
    """Spot direction in radians (clockwise on screen from +x); None = point light."""
    cone: float = math.radians(30)
    """Spot half-angle."""
    cone_softness: float = math.radians(8)
    shadow_softness: float = 0.0
    """Penumbra width in radians; 0 gives hard shadows."""
    cast_shadows: bool = True

    def rgb(self) -> np.ndarray:
        return parse_color(self.color, 3).astype(np.float32) / 255.0


def _shadow_bins(radius: float) -> int:
    return int(min(max(2 * math.pi * radius, 256), 8192))


def _shadow_map(light: Light, occluders: np.ndarray, bins: int) -> Optional[np.ndarray]:
    """Nearest occluder distance per angular bin around the light (inf = open)."""
    h, w = occluders.shape
    r = light.radius
    x0, y0 = max(int(light.x - r), 0), max(int(light.y - r), 0)
    x1, y1 = min(int(light.x + r) + 2, w), min(int(light.y + r) + 2, h)
    if x0 >= x1 or y0 >= y1:
        return None
    oy, ox = np.nonzero(occluders[y0:y1, x0:x1])
    if len(ox) == 0:
        return None
    ox = ox.astype(np.float32) + x0 - light.x
    oy = oy.astype(np.float32) + y0 - light.y
    smap = np.full(bins, np.inf, dtype=np.float32)
    # Sample the centre and four corners so each pixel covers its full angular width.
    for sx, sy in ((0, 0), (-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)):
        px, py = ox + sx, oy + sy
        angle_bins = ((np.arctan2(py, px) + math.pi) * (bins / (2 * math.pi))).astype(int) % bins
        np.minimum.at(smap, angle_bins, np.hypot(px, py))
    return smap


def light_map(width: int, height: int, lights: Sequence[Light], *,
              occluders: Optional[np.ndarray] = None, ambient: Color | float = 0.1,
              scale: float = 0.5) -> np.ndarray:
    """(height, width, 3) float light map: ambient plus every light's contribution."""
    lw, lh = max(1, round(width * scale)), max(1, round(height * scale))
    sx, sy = width / lw, height / lh
    if isinstance(ambient, (int, float)):
        amb = np.full(3, float(ambient), dtype=np.float32)
    else:
        amb = parse_color(ambient, 3).astype(np.float32) / 255.0
    acc = np.broadcast_to(amb, (lh, lw, 3)).copy()
    if occluders is not None:
        occluders = np.asarray(occluders, dtype=bool)
        if occluders.shape != (height, width):
            raise ValueError(f"occluder mask must be {(height, width)}, got {occluders.shape}")
    bias = 0.75 * max(sx, sy) + 0.5

    for light in lights:
        r = light.radius
        # Low-res pixel window covering the light's reach.
        j0 = max(int((light.x - r) / sx), 0)
        j1 = min(int((light.x + r) / sx) + 2, lw)
        i0 = max(int((light.y - r) / sy), 0)
        i1 = min(int((light.y + r) / sy) + 2, lh)
        if j0 >= j1 or i0 >= i1:
            continue
        I, J = np.mgrid[i0:i1, j0:j1].astype(np.float32)
        dx = (J + 0.5) * sx - 0.5 - light.x
        dy = (I + 0.5) * sy - 0.5 - light.y
        d = np.hypot(dx, dy)
        k = np.clip(1.0 - (d / r) ** 2, 0.0, 1.0) ** 2 * light.intensity

        if light.direction is not None:
            rel = np.abs((np.arctan2(dy, dx) - light.direction + math.pi) % (2 * math.pi) - math.pi)
            soft = max(light.cone_softness, 1e-6)
            k = k * smoothstep(light.cone + soft / 2, light.cone - soft / 2, rel)

        if occluders is not None and light.cast_shadows:
            bins = _shadow_bins(r)
            smap = _shadow_map(light, occluders, bins)
            if smap is not None:
                center = ((np.arctan2(dy, dx) + math.pi) * (bins / (2 * math.pi))).astype(int)
                taps = max(0, round(light.shadow_softness / 2 * bins / (2 * math.pi)))
                step = max(1, taps // 6)  # at most ~13 lookups per pixel
                offsets = range(-taps, taps + 1, step)
                visible = np.zeros_like(d)
                for off in offsets:
                    visible += d <= smap[(center + off) % bins] + bias
                k = k * (visible / len(offsets))

        acc[i0:i1, j0:j1] += k[:, :, None] * light.rgb()

    if (lh, lw) != (height, width):
        acc = resize_bilinear(acc, height, width)
    return acc


def apply_lighting(canvas: Canvas, lights: Sequence[Light], *,
                   occluders: Optional[np.ndarray] = None, ambient: Color | float = 0.1,
                   scale: float = 0.5, white: Optional[float] = None) -> np.ndarray:
    """Multiply the canvas by its light map (values above 1 brighten); returns the map.

    `white` enables Reinhard tone mapping: light levels roll off smoothly
    and only a level of `white` or more maps to full brightness (1.0 stays
    1.0 when white=1), so overlapping lights don't clip to flat white.
    """
    lm = light_map(canvas.width, canvas.height, lights, occluders=occluders,
                   ambient=ambient, scale=scale)
    if white is not None:
        lm = tonemap(lm, white)
    factor = lm if canvas.channels == 3 else lm.mean(axis=2, keepdims=True)
    canvas.set_float(canvas.to_float() * factor)
    return lm


def tonemap(light: np.ndarray, white: float = 2.0) -> np.ndarray:
    """Extended Reinhard curve: compresses highlights, reaching 1.0 at `white`."""
    return light * (1.0 + light / (white * white)) / (1.0 + light)


def glow(canvas: Canvas, x: float, y: float, radius: float, color, *,
         intensity: float = 1.0, falloff: float = 2.2) -> None:
    """Additive radial glow, e.g. to show the light source itself."""
    x0, y0 = max(int(x - radius), 0), max(int(y - radius), 0)
    x1, y1 = min(int(x + radius) + 2, canvas.width), min(int(y + radius) + 2, canvas.height)
    if x0 >= x1 or y0 >= y1:
        return
    Y, X = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    k = np.clip(1.0 - np.hypot(X - x, Y - y) / radius, 0.0, 1.0) ** falloff * intensity
    canvas.blend(x0, y0, np.clip(k, 0.0, 1.0), color, mode="add")


def bloom(canvas: Canvas, *, threshold: float = 0.7, sigma: float = 6.0,
          strength: float = 0.8) -> None:
    """Make bright areas bleed light into their surroundings."""
    f = canvas.to_float()
    lum = f.mean(axis=2) if canvas.channels != 3 else f @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    bright = f * smoothstep(threshold, 1.0, lum)[:, :, None]
    canvas.set_float(f + gaussian_blur(bright, sigma) * strength)


def vignette(canvas: Canvas, *, strength: float = 0.5, inner: float = 0.45,
             outer: float = 1.0, color: Color = 0) -> None:
    """Darken (or tint towards `color`) the edges; radius 1 = the corners."""
    h, w = canvas.height, canvas.width
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((X - (w - 1) / 2) / (w / 2), (Y - (h - 1) / 2) / (h / 2)) / math.sqrt(2)
    canvas.blend(0, 0, smoothstep(inner, outer, r) * strength, color)
