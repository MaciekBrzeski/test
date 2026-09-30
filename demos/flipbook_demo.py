"""Milestone 3 demo: an animated A4 PDF that plays as a flipbook.

    python demos/flipbook_demo.py [output.pdf] [--fps 12] [--seconds 4] [--dpi 144]

Open the result in Adobe Acrobat or Reader: it goes full screen and the
frames advance on their own. To loop, enable Preferences > Full Screen >
"Loop after last page". Viewers that ignore page durations (browsers,
most mobile apps) show the same frames as pages you scroll through.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine_showcase import lit_scene  # noqa: E402

from pixelpdf import Canvas  # noqa: E402
from pixelpdf.engine import raster as R  # noqa: E402
from pixelpdf.engine import spinners, text_fx as fx  # noqa: E402
from pixelpdf.engine.anim import Keyframes  # noqa: E402
from pixelpdf.engine.font import draw_text, measure_text  # noqa: E402
from pixelpdf.engine.particles import Emitter, ParticleSystem  # noqa: E402
from pixelpdf.flipbook import Flipbook  # noqa: E402
from pixelpdf.pdf.image import encode_image  # noqa: E402

PAPER = "#f4f1ea"
INK = "#1d1d2b"
MUTED = "#6b6b7b"
ACCENT = "#e4572e"
BLUE = "#2e86de"


def title_page(book: Flipbook, seconds: float, frames: int) -> Canvas:
    c = book.new_frame(PAPER)
    W, H = c.width, c.height
    draw_text(c, "pixelpdf", W // 2, H // 3 - 60, INK, scale=12, align="center",
              colors=lambda i: fx.hsv(0.02 + i * 0.07, 0.75, 0.85))
    draw_text(c, "flipbook", W // 2, H // 3 + 60, ACCENT, scale=6, align="center")
    lines = [
        f"{frames} frames, {seconds:g} seconds, every pixel computed in Python.",
        "",
        "Adobe Acrobat / Reader: the document opens full screen and",
        "plays by itself. Press the right arrow to start. To loop, turn on",
        "Preferences > Full Screen > Loop after last page.",
        "",
        "Other viewers: scroll through the pages.",
    ]
    draw_text(c, "\n".join(lines), W // 2, H // 2 + 40, MUTED, scale=2, align="center")
    spinners.arc_spinner(c, W / 2, H * 0.8, 40, 0.4, BLUE, track="#dde4f5")
    return c


class Scene:
    """Everything that animates on the frame pages.

    The layout shows the three cases a flipbook handles differently:
    detailed static art (stored once, in the keyframe), animation laid
    over it (only the changed pixels are stored), and looping content
    (each distinct patch is stored once and reused on later cycles).
    """

    def __init__(self, book: Flipbook, fps: float, total: int):
        self.fps, self.total = fps, total
        self.m = m = 48
        self.inner = inner = book.width - 2 * m
        self.top = m + 90
        self.backdrop_h = 500
        # Detailed, noisy art: expensive to store, so it should be stored once.
        self.backdrop = lit_scene(inner, self.backdrop_h, 0.6, texture=True)
        self.half = (inner - 24) // 2
        self.row_h = 420
        self.sparks = ParticleSystem(
            gravity=(0, 380), drag=0.2, bounds=(0, 0, inner - 1, self.backdrop_h - 1),
            restitution=0.45, friction=0.1, seed=4,
            colors=[(0, "#fff6c8"), (0.3, "#ffb347"), (0.75, "#ff5e3a"), (1, "#5a1020")],
            fade=[(0, 1), (0.8, 0.9), (1, 0)])
        self.sparks.add_emitter(Emitter(inner * 0.5, self.backdrop_h * 0.35, rate=260,
                                        angle=-math.pi / 2, spread=0.7, speed=(150, 300),
                                        life=(1.2, 2.2), size=(1.0, 2.2), jitter=3))
        for _ in range(15):
            self.sparks.step(1 / fps)

    def draw(self, c: Canvas, i: int) -> None:
        t = i / self.fps
        W, H = c.width, c.height
        m, inner, half = self.m, self.inner, self.half

        draw_text(c, "Live from a PDF", m, m, INK, scale=5)
        draw_text(c, "each page is one frame; only pixels that differ from a keyframe are stored",
                  m, m + 50, MUTED, scale=2)

        # 1. Static detailed backdrop with sparks on top.
        y = self.top
        self.sparks.step(1 / self.fps)
        panel = self.backdrop.copy()
        self.sparks.render(panel, mode="add")
        c.blit(panel, m, y)
        caption(c, "static art, stored once + sparks, stored as changed pixels", m + 12, y + 12)
        y += self.backdrop_h + 24

        # 2a. Moving light: every pixel changes, so this is stored in full each frame.
        # Rendered as 2x2-pixel blocks, which compresses ~2.5x better.
        scene = lit_scene(half // 2, self.row_h // 2, t, texture=False).upscale(2)
        c.blit(scene, m, y)
        caption(c, "moving light: stored every frame", m + 12, y + 12)

        # 2b. Looping content: after one cycle every patch is a repeat.
        x = m + half + 24
        cw = inner - half - 24
        R.rect(c, x, y, cw, self.row_h, "#ffffff", radius=16)
        kinds = [(spinners.arc_spinner, BLUE, {"track": "#e5e9f2"}),
                 (spinners.dots_spinner, ACCENT, {}),
                 (spinners.bars_spinner, INK, {}),
                 (spinners.pulse_spinner, "#27ae60", {}),
                 (spinners.orbit_spinner, "#8e44ad", {}),
                 (spinners.arc_spinner, ACCENT, {"period": 1.0})]
        cell = cw / 3
        for k, (fn, color, kw) in enumerate(kinds):
            fn(c, x + cell * (k % 3) + cell / 2, y + 80 + (k // 3) * 120, 40, t, color, **kw)
        draw_text(c, "Wave!", x + cw // 2, y + 270, scale=6, align="center",
                  offsets=fx.wave(t, amplitude=8, speed=1.0), colors=fx.rainbow(t, speed=1.0, spread=0.2))
        bx = Keyframes([(0, 0.0), (1.0, 1.0, "out_bounce"), (2.0, 0.0, "in_out_cubic")], loop=2.0)(t)
        R.circle(c, x + 40 + bx * (cw - 80), y + self.row_h - 40, 18, ACCENT)
        draw_text(c, "loops: patches reused after one cycle", x + cw // 2, y + 16, MUTED,
                  scale=2, align="center")
        y += self.row_h + 24

        # 3. Typewriter caption and a progress bar.
        text = fx.typewriter("Typed one character at a time, straight into the page.", t, cps=16)
        draw_text(c, text, m, y, INK, scale=3)
        y = H - m - 18
        R.rect(c, m, y, inner, 18, "#e0dcd2", radius=9)
        R.rect(c, m, y, max(18, round(inner * (i + 1) / self.total)), 18, BLUE, radius=9)
        label = f"frame {i + 1}/{self.total}   t = {t:4.2f} s"
        draw_text(c, label, W - m, y - 24, MUTED, scale=2, align="right")


def caption(c: Canvas, text: str, x: int, y: int) -> None:
    w, h = measure_text(text, 2)
    R.rect(c, x, y, w + 16, h + 10, "#101018", radius=8, opacity=0.7)
    draw_text(c, text, x + 8, y + 5, "#f0f0f8", scale=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="out/flipbook.pdf")
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--dpi", type=float, default=144)
    args = parser.parse_args()

    start = time.time()
    book = Flipbook(dpi=args.dpi, fps=args.fps, title="pixelpdf — flipbook demo")
    total = max(1, round(args.seconds * args.fps))
    book.add_frame(title_page(book, args.seconds, total), advance=False)

    scene = Scene(book, args.fps, total)
    full_frame_bytes = 0
    for i in range(total):
        frame = book.new_frame(PAPER)
        scene.draw(frame, i)
        if i % 12 == 0:  # sample the cost of storing whole frames, for comparison
            full_frame_bytes += len(encode_image(frame.pixels).data) * min(12, total - i)
        book.add_frame(frame)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    s = book.stats
    size = out.stat().st_size
    print(f"wrote {out}: {s.frames} pages, {size / 1e6:.1f} MB in {time.time() - start:.1f} s")
    print(f"  keyframes {s.keyframes}, patches {s.patches} ({s.reused_images} reused), "
          f"repeated frames {s.reused_frames}")
    print(f"  whole frames would take about {full_frame_bytes / 1e6:.1f} MB "
          f"({full_frame_bytes / size:.1f}x larger)")


if __name__ == "__main__":
    main()
