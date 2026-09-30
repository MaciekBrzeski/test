"""Milestone 5: one PDF showing everything pixelpdf does.

    python demos/showcase.py [output.pdf] [--frames 36] [--fps 12]

Pages, in order:
  cover            title, a rendered scene, clickable contents
  pixel-exact art  gradient, colour wheel, lit sphere, Mandelbrot, 1-px patterns
  engine           primitives, text effects, spinners, lighting, particles
  flipbook         an intro page, then one page per frame (auto-plays in
                   Acrobat's full screen mode)
  games            Snake, Breakout and Fireworks, each live on its own page
  viewer support   what works where, and what was actually tested
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import engine_showcase  # noqa: E402
import flipbook_demo  # noqa: E402
import static_page  # noqa: E402

from pixelpdf import Canvas, Composer, Document  # noqa: E402
from pixelpdf.engine import raster as R  # noqa: E402
from pixelpdf.engine import text_fx as fx  # noqa: E402
from pixelpdf.engine.font import draw_text, measure_text  # noqa: E402
from pixelpdf.engine.light import bloom, glow, vignette  # noqa: E402
from pixelpdf.engine.particles import Emitter, ParticleSystem  # noqa: E402
from pixelpdf.interactive import InteractiveDocument  # noqa: E402
from pixelpdf.interactive.games import GAMES, add_game_page  # noqa: E402

DPI = 144
NIGHT = "#101018"
PAPER = "#f4f1ea"
INK = "#1d1d2b"
MUTED = "#6b6b7b"
SOFT = "#9a9ab0"
LIGHT = "#e8e8f0"
ACCENT = "#e4572e"

# Viewer support. Status: tested (checked here), expected (standard PDF
# feature, not tested here), pages (shown as ordinary pages, no motion),
# no, unknown.
VIEWERS = ["Chrome / Edge", "Acrobat / Reader", "Firefox", "Preview, mobile"]
SUPPORT = [
    ("Pixel-exact pages", ["tested", "expected", "expected", "expected"]),
    ("Flipbook auto-play", ["pages", "expected", "unknown", "pages"]),
    ("Games (JavaScript)", ["tested", "expected", "unknown", "no"]),
    ("Links, bookmarks", ["tested", "expected", "expected", "expected"]),
]
STATUS = {
    "tested": ("TESTED", "#2ecc71"),
    "expected": ("EXPECTED", "#9be7b4"),
    "pages": ("PAGES ONLY", "#feca57"),
    "unknown": ("UNTESTED", "#9a9ab0"),
    "no": ("NO", "#ff6b6b"),
}


def hero(w: int, h: int) -> tuple[Canvas, int]:
    """The cover picture: a lit room with a shower of sparks; returns (canvas, sparks)."""
    scene = engine_showcase.lit_scene(w, h, 0.9, texture=True)
    ps = ParticleSystem(gravity=(0, 380), drag=0.2, bounds=(0, 0, w - 1, h - 1),
                        restitution=0.45, seed=9,
                        colors=[(0, "#fff6c8"), (0.3, "#ffb347"), (0.75, "#ff5e3a"), (1, "#5a1020")],
                        fade=[(0, 1), (0.8, 0.9), (1, 0)])
    ps.add_emitter(Emitter(w * 0.62, h * 0.3, rate=500, angle=-math.pi / 2, spread=0.8,
                           speed=(150, 320), life=(1.2, 2.4), size=(1.0, 2.4), jitter=3))
    for _ in range(50):
        ps.step(1 / 30)
    ps.render(scene, mode="add")
    glow(scene, w * 0.62, h * 0.3, 40, "#ffdd99", intensity=0.9)
    bloom(scene, threshold=0.6, sigma=6, strength=0.8)
    return scene, len(ps)


def cover(contents: list[tuple[str, str, int]]) -> tuple[Canvas, list[tuple[tuple, int]]]:
    """Returns the cover canvas and the (rect, target page) of each contents row."""
    c = Document(dpi=DPI).new_page(background=NIGHT).canvas
    W, H = c.width, c.height
    m = 48
    inner = W - 2 * m
    draw_text(c, "pixelpdf", W // 2, 70, scale=16, align="center",
              colors=lambda i: fx.hsv(0.02 + i * 0.075, 0.7, 0.95))
    draw_text(c, "a PDF where every pixel is computed", W // 2, 240, SOFT, scale=3, align="center")

    h = 560
    y = 320
    pic, sparks = hero(inner, h)
    R.rect(c, m - 4, y - 4, inner + 8, h + 8, "#34344a", radius=10)
    c.blit(pic, m, y)
    draw_text(c, f"rendered in Python: 3 lights, soft shadows, {sparks} sparks, bloom",
              W // 2, y + h + 14, "#6b6b80", scale=2, align="center")

    y += h + 60
    draw_text(c, "CONTENTS", m, y, LIGHT, scale=4)
    R.rect(c, m, y + 42, measure_text("CONTENTS", 4)[0], 3, ACCENT)
    y += 70
    rows = []
    row_h = 68
    for i, (title, blurb, page) in enumerate(contents):
        top = y + i * row_h
        if i % 2 == 0:
            R.rect(c, m, top, inner, row_h, "#16161f", radius=8)
        draw_text(c, f"{i + 1}", m + 20, top + 17, ACCENT, scale=4)
        draw_text(c, title, m + 80, top + 10, LIGHT, scale=3)
        draw_text(c, blurb, m + 80, top + 44, "#7b7b90", scale=2)
        draw_text(c, f"p. {page + 1}", W - m - 20, top + 22, SOFT, scale=3, align="right")
        rows.append(((m, top, inner, row_h), page))
    draw_text(c, "Click a row to jump there. Best in Chrome, Edge or Adobe Acrobat/Reader.",
              W // 2, H - 70, "#6b6b80", scale=2, align="center")
    vignette(c, strength=0.4)
    return c, rows


def section_page(title: str, lines: list[str], badge: str) -> Canvas:
    c = Document(dpi=DPI).new_page(background=PAPER).canvas
    W, H = c.width, c.height
    draw_text(c, badge, W // 2, H // 3 - 90, ACCENT, scale=4, align="center")
    draw_text(c, title, W // 2, H // 3 - 30, INK, scale=10, align="center")
    draw_text(c, "\n".join(lines), W // 2, H // 3 + 110, MUTED, scale=3, align="center", leading=6)
    return c


def support_page(pages: int) -> Canvas:
    c = Document(dpi=DPI).new_page(background=PAPER).canvas
    W, H = c.width, c.height
    m = 60
    draw_text(c, "Which viewer does what", m, m, INK, scale=5)
    R.rect(c, m, m + 50, measure_text("Which viewer does what", 5)[0], 4, ACCENT)

    first = 300
    col = (W - 2 * m - first) // len(VIEWERS)
    y = m + 110
    for j, name in enumerate(VIEWERS):
        draw_text(c, name, m + first + j * col + col // 2, y, INK, scale=2, align="center")
    y += 40
    for i, (feature, statuses) in enumerate(SUPPORT):
        R.rect(c, m, y, W - 2 * m, 70, "#ffffff" if i % 2 == 0 else "#ece8de", radius=8)
        draw_text(c, feature, m + 16, y + 26, INK, scale=2)
        for j, status in enumerate(statuses):
            label, color = STATUS[status]
            cx = m + first + j * col + col // 2
            tw = measure_text(label, 2)[0]
            R.rect(c, cx - tw // 2 - 12, y + 16, tw + 24, 38, color, radius=19)
            draw_text(c, label, cx, y + 27, INK, scale=2, align="center")
        y += 80

    y += 30
    legend = [
        ("TESTED", "checked in this project's test suite (headless Chromium / PDFium)"),
        ("EXPECTED", "standard PDF feature the viewer documents; not run here"),
        ("PAGES ONLY", "frames show as ordinary pages you scroll or click through"),
        ("UNTESTED", "partial support is likely; not verified"),
        ("NO", "the viewer does not run PDF JavaScript"),
    ]
    for label, text in legend:
        color = next(v[1] for v in STATUS.values() if v[0] == label)
        R.rect(c, m, y, 26, 26, color, radius=6)
        draw_text(c, label, m + 40, y + 6, INK, scale=2)
        draw_text(c, text, m + 220, y + 6, MUTED, scale=2)
        y += 40

    y += 40
    notes = [
        "To play the flipbook in Acrobat: go to its first frame and press",
        "Ctrl+L (Cmd+L on a Mac). Frames advance by themselves, then stop",
        "at the games. Games run in Chrome, Edge and Acrobat: click the",
        "pale key box and type, or press the on-screen buttons. A game",
        "only runs while its page is the one in view.",
    ]
    draw_text(c, "HOW TO WATCH AND PLAY", m, y, INK, scale=3)
    y += 44
    draw_text(c, "\n".join(notes), m, y, MUTED, scale=2, leading=5)

    draw_text(c, f"{pages} pages, generated by demos/showcase.py with pixelpdf.",
              W // 2, H - 80, MUTED, scale=2, align="center")
    return c


def build(frames: int, fps: float) -> Composer:
    book = Composer(dpi=DPI, title="pixelpdf showcase")

    # Page numbers are fixed by the order below; the cover needs them up front.
    p_art, p_engine, p_flip = 1, 2, 3
    p_games = p_flip + 1 + frames
    p_support = p_games + len(GAMES)
    contents = [
        ("Pixel-exact art", "gradients, a lit sphere, a fractal and 1-px test patterns", p_art),
        ("The engine", "primitives, text effects, spinners, lighting, particles", p_engine),
        ("Flipbook", f"{frames} frames that play by themselves in Acrobat full screen", p_flip),
    ] + [(GAMES[n].title.title(), GAMES[n].tagline, p_games + i) for i, n in enumerate(GAMES)] + [
        ("Viewer support", "what works where, and what was tested", p_support),
    ]
    cover_canvas, links = cover(contents)
    assert book.add_canvas(cover_canvas) == 0

    assert book.add_canvas(static_page.build(DPI).pages[0].canvas) == p_art
    engine_doc = Document(dpi=DPI)
    engine_showcase.build_page1(engine_doc)
    assert book.add_canvas(engine_doc.pages[0].canvas) == p_engine

    assert book.add_canvas(section_page("Flipbook", [
        f"The next {frames} pages are frames of one animation.",
        "In Adobe Acrobat or Reader press Ctrl+L on the first",
        "frame: they play at {:g} fps and stop at the games.".format(fps),
        "Elsewhere, scroll through them like a flip book.",
    ], "SECTION 3")) == p_flip
    anim = book.flipbook(fps=fps)
    scene = flipbook_demo.Scene(anim, fps, frames)
    for i in range(frames):
        frame = anim.new_frame(flipbook_demo.PAPER)
        scene.draw(frame, i)
        anim.add_frame(frame)

    games = InteractiveDocument(dpi=DPI, fps=30, seed=7)
    for name in GAMES:
        add_game_page(games, name)
    assert book.add_interactive(games) == list(range(p_games, p_games + len(GAMES)))

    total = p_support + 1
    assert book.add_canvas(support_page(total)) == p_support

    for rect, target in links:
        book.link(0, rect, target)
    book.bookmark("Cover", 0)
    for title, _, page in contents:
        book.bookmark(title, page)
    return book


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="out/showcase.pdf")
    parser.add_argument("--frames", type=int, default=36)
    parser.add_argument("--fps", type=float, default=12)
    args = parser.parse_args()
    start = time.time()
    book = build(args.frames, args.fps)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    book.save(out)
    print(f"wrote {out}: {len(book)} pages, {out.stat().st_size / 1e6:.1f} MB "
          f"in {time.time() - start:.0f} s")


if __name__ == "__main__":
    main()
