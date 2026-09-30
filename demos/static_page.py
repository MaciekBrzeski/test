"""Milestone 1 demo: one A4 page where every pixel is computed in code.

    python demos/static_page.py [output.pdf] [--dpi 144]

Panels (top to bottom): hue/value gradient, colour wheel, lit sphere,
Mandelbrot set, and a strip of 1-px test patterns (checkerboard, lines,
single pixels) that only survive if the PDF shows pixels exactly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pixelpdf import Document  # noqa: E402


def hsv_to_rgb(h, s, v):
    """Vectorised HSV -> RGB; h, s, v in [0, 1]. Returns float RGB in [0, 1]."""
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def to_u8(rgb):
    return np.clip(np.round(rgb * 255), 0, 255).astype(np.uint8)


def gradient_panel(w, h):
    y, x = np.mgrid[0:h, 0:w]
    return to_u8(hsv_to_rgb(x / w, np.ones_like(x, float), 1 - 0.8 * y / h))


def color_wheel(size, bg):
    y, x = np.mgrid[0:size, 0:size] - (size - 1) / 2
    r = np.hypot(x, y) / (size / 2)
    rgb = hsv_to_rgb((np.arctan2(y, x) / (2 * np.pi)) % 1, np.clip(r, 0, 1), np.ones_like(r))
    out = to_u8(rgb)
    out[r > 1] = bg
    return out


def lit_sphere(size, bg):
    """Phong-shaded sphere: diffuse + specular from a light at the upper left."""
    y, x = (np.mgrid[0:size, 0:size] - (size - 1) / 2) / (size / 2 * 0.92)
    inside = x * x + y * y <= 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    normal = np.stack([x, -y, z], axis=-1)
    light = np.array([-0.5, 0.6, 0.62])
    light /= np.linalg.norm(light)
    diffuse = np.clip(normal @ light, 0, 1)
    reflect = 2 * diffuse[..., None] * normal - light
    specular = np.clip(reflect[..., 2], 0, 1) ** 40
    base = np.array([0.95, 0.35, 0.2])
    rgb = 0.08 + base * diffuse[..., None] * 0.9 + specular[..., None] * 0.9
    out = to_u8(rgb)
    # Soft floor shadow, then the sphere on top.
    sy, sx = (np.mgrid[0:size, 0:size] - (size - 1) / 2) / (size / 2)
    shadow = np.clip(1 - np.hypot((sx - 0.25) / 0.9, (sy - 0.9) / 0.18), 0, 1) ** 1.5
    floor = (np.asarray(bg, float) * (1 - 0.5 * shadow[..., None])).astype(np.uint8)
    return np.where(inside[..., None], out, floor)


def mandelbrot(w, h, iterations=200):
    y, x = np.mgrid[0:h, 0:w]
    c = (-0.7435 + (x - w / 2) * (0.0045 / w)) + 1j * (0.1314 + (y - h / 2) * (0.0045 / w))
    z = np.zeros_like(c)
    count = np.full(c.shape, iterations, dtype=float)
    alive = np.ones(c.shape, dtype=bool)
    for i in range(iterations):
        z[alive] = z[alive] ** 2 + c[alive]
        escaped = alive & (np.abs(z) > 4)
        count[escaped] = i + 1 - np.log2(np.log2(np.abs(z[escaped])))
        alive &= ~escaped
    t = count / iterations
    rgb = hsv_to_rgb((0.62 + 3 * t) % 1, np.full_like(t, 0.75), np.sqrt(np.clip(t * 4, 0, 1)))
    rgb[alive] = 0
    return to_u8(rgb)


def test_patterns(w, h):
    """1-px detail that blurs to grey if the viewer or encoder isn't exact."""
    out = np.full((h, w, 3), 255, dtype=np.uint8)
    y, x = np.mgrid[0:h, 0:w]
    q = w // 4
    out[:, :q][((x + y) % 2 == 0)[:, :q]] = 0                              # checkerboard
    out[:, q:2 * q][(y % 2 == 0)[:, q:2 * q]] = (220, 30, 30)               # horizontal lines
    out[:, 2 * q:3 * q][(x % 2 == 0)[:, 2 * q:3 * q]] = (30, 30, 220)       # vertical lines
    out[:, 3 * q:] = 0
    out[:, 3 * q:][((x % 8 == 3) & (y % 8 == 3))[:, 3 * q:]] = 255          # isolated pixels
    return out


def build(dpi: float) -> Document:
    doc = Document(dpi=dpi, title="pixelpdf — static page demo")
    page = doc.new_page(background="#f4f1ea")
    px, canvas = page.canvas.pixels, page.canvas
    W, H = canvas.width, canvas.height
    bg = canvas.color("#f4f1ea")
    m = W // 16  # margin

    def place(img, x, y):
        px[y:y + img.shape[0], x:x + img.shape[1]] = img

    inner = W - 2 * m
    y = m
    place(gradient_panel(inner, H // 10), m, y)
    y += H // 10 + m

    half = (inner - m) // 2
    place(color_wheel(half, bg), m, y)
    place(lit_sphere(half, bg), m + half + m, y)
    y += half + m

    mh = H - y - m - H // 14 - m
    place(mandelbrot(inner, mh), m, y)
    y += mh + m

    place(test_patterns(inner, H - y - m), m, y)
    # 1-px frame around the whole page, flush with the edge.
    px[0, :], px[-1, :], px[:, 0], px[:, -1] = 0, 0, 0, 0
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="out/static_page.pdf")
    parser.add_argument("--dpi", type=float, default=144)
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(args.dpi).save(out)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
