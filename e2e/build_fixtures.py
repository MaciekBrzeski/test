"""Build the PDFs the browser tests open, plus a JSON description of each.

    python3 e2e/build_fixtures.py [outdir]     (default: e2e/.fixtures)

Every fixture page has a distinctive background colour so a test can find
the page on screen and map canvas pixels to screen pixels. Geometry the
tests need (link areas, display cells, HUD boxes, buttons) is written to
fixtures.json, so the specs never hard-code layout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pixelpdf import Canvas, Composer, Document  # noqa: E402
from pixelpdf.engine import raster as R  # noqa: E402
from pixelpdf.flipbook import Flipbook  # noqa: E402
from pixelpdf.interactive import InteractiveDocument  # noqa: E402
from pixelpdf.interactive.games import GAMES, add_game_page  # noqa: E402

DPI = 144
W, H = 1190, 1684
MARK = 12          # px; magenta squares in both top corners of every page
MAGENTA = "#ff00ff"


def mark(canvas: Canvas) -> Canvas:
    """Corner markers let the tests find the page on screen exactly."""
    canvas.fill_rect(0, 0, MARK, MARK, MAGENTA)
    canvas.fill_rect(canvas.width - MARK, 0, MARK, MARK, MAGENTA)
    return canvas


def hexrgb(color: str) -> list[int]:
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def static_fixture(out: Path) -> dict:
    """Flat colour blocks, a 1-px checkerboard and seeded noise on a known background."""
    bg = "#203040"
    doc = Document(dpi=DPI)
    c = doc.new_page(background=bg).canvas
    blocks = {"red": "#ff0000", "green": "#00ff00", "blue": "#0000ff", "white": "#ffffff",
              "orange": "#e4572e"}
    rects = {}
    for i, (name, color) in enumerate(blocks.items()):
        rect = [100 + i * 200, 100, 160, 160]
        R.rect(c, *rect, color)
        rects[name] = {"rect": rect, "rgb": hexrgb(color)}
    checker = [100, 400, 400, 300]
    y, x = np.mgrid[0:checker[3], 0:checker[2]]
    c.pixels[400:700, 100:500] = (((x + y) % 2) * 255)[:, :, None].astype(np.uint8)
    noise = [600, 400, 400, 300]
    rng = np.random.default_rng(42)
    c.pixels[400:700, 600:1000] = rng.integers(0, 256, (300, 400, 3), dtype=np.uint8)
    mark(c)
    doc.save(out / "static.pdf")
    (out / "static_noise.rgb").write_bytes(c.pixels[400:700, 600:1000].tobytes())
    return {"file": "static.pdf", "bg": hexrgb(bg), "width": W, "blocks": rects,
            "checker": checker, "noise": noise, "noise_file": "static_noise.rgb"}


FRAME_COLORS = ["#c0392b", "#27ae60", "#2980b9", "#8e44ad", "#f39c12", "#16a085"]


def flipbook_fixture(out: Path) -> dict:
    """Six frames, each a different background, with a square moving right."""
    book = Flipbook(dpi=DPI, fps=4, fullscreen=False, title="fixture flipbook")
    squares = []
    for i, color in enumerate(FRAME_COLORS):
        f = mark(book.new_frame(color))
        sq = [200 + 120 * i, 700, 100, 100]
        R.rect(f, *sq, "#ffffff")
        squares.append(sq)
        book.add_frame(f)
    book.save(out / "flipbook.pdf")
    return {"file": "flipbook.pdf", "frames": [hexrgb(c) for c in FRAME_COLORS],
            "squares": squares, "fps": 4, "width": W}


def game_geometry(page, name: str) -> dict:
    d = page.display_spec
    fields = {f.name: list(f.rect) for f in page.fields}
    return {"display": [d.x, d.y, d.width, d.height], "cell": d.cell, "cols": d.cols,
            "rows": d.rows, "keys": fields.get("keys"),
            "huds": {n[4:]: r for n, r in fields.items() if n.startswith("hud_")},
            "buttons": [{"rect": list(f.rect), "key": f.spec["key"], "label": f.spec["label"]}
                        for f in page.fields if f.kind == "button"]}


def games_fixtures(out: Path) -> dict:
    result = {}
    for name in GAMES:
        doc = InteractiveDocument(dpi=DPI, fps=30, seed=7)
        page = add_game_page(doc, name)
        mark(page.canvas)
        doc.save(out / f"{name}.pdf")
        result[name] = {"file": f"{name}.pdf", "bg": [16, 16, 24], "width": W,
                        **game_geometry(page, name)}
    return result


# A test game: lights the two corner cells and the centre, so a test can
# check that cells land exactly where the layout says, in every viewer.
GEOMETRY_GAME = """PX.run({init: function (px) {
  px.set(0, 0, 1); px.set(px.W - 1, px.H - 1, 2); px.set(Math.floor(px.W / 2), Math.floor(px.H / 2), 3);
}});"""

# A test game that counts the frames it has run as a growing bar (one cell
# per 10 frames), so a test can tell whether it ran while its page was hidden.
COUNTER_GAME = """PX.run({update: function (px) {
  var n = Math.min(px.W * px.H, Math.floor(px.frame / 10));
  for (var i = 0; i < n; i++) px.set(i % px.W, Math.floor(i / px.W), 1);
  px.hud('n', 'FRAMES ' + px.frame);
}});"""


def geometry_fixture(out: Path) -> dict:
    doc = InteractiveDocument(dpi=DPI, fps=20)
    page = doc.new_page(background="#101018")
    mark(page.canvas)
    d = page.display(150, 300, 20, 12, 40, [None, "#ff0000", "#00ff00", "#0000ff"])
    page.set_game(GEOMETRY_GAME)
    doc.save(out / "geometry.pdf")
    return {"file": "geometry.pdf", "bg": [16, 16, 24], "width": W,
            "display": [d.x, d.y, d.width, d.height], "cell": d.cell, "cols": d.cols,
            "rows": d.rows, "cells": [[0, 0, [255, 0, 0]], [d.cols - 1, d.rows - 1, [0, 255, 0]],
                                      [d.cols // 2, d.rows // 2, [0, 0, 255]]]}


def compose_fixture(out: Path) -> dict:
    """Cover with a link to page 3, a plain middle page, and a frame-counting game."""
    book = Composer(dpi=DPI, title="fixture composer")
    cover = mark(Canvas(W, H, background="#203040"))
    link = [100, 100, 500, 200]
    R.rect(cover, *link, "#e4572e")
    book.add_canvas(cover)
    book.add_canvas(mark(Canvas(W, H, background="#2e4030")))
    games = InteractiveDocument(dpi=DPI, fps=30)
    page = games.new_page(background="#301830")
    mark(page.canvas)
    d = page.display(100, 300, 40, 10, 25, [None, "#ffe66d"])
    page.hud("n", 100, 200, 600, 50, color="#ffffff")
    page.set_game(COUNTER_GAME)
    (game_page,) = book.add_interactive(games)
    book.link(0, link, game_page)
    book.bookmark("Cover", 0)
    book.bookmark("Game", game_page)
    book.save(out / "compose.pdf")
    return {"file": "compose.pdf", "width": W, "cover_bg": [32, 48, 64], "game_bg": [48, 24, 48],
            "link": link, "game_page": game_page, "display": [d.x, d.y, d.width, d.height],
            "cell": d.cell, "cols": d.cols, "rows": d.rows, "bar": [255, 230, 109],
            "frames_per_cell": 10}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "e2e" / ".fixtures"
    out.mkdir(parents=True, exist_ok=True)
    spec = {
        "dpi": DPI, "marker": {"size": MARK, "rgb": hexrgb(MAGENTA)},
        "static": static_fixture(out),
        "flipbook": flipbook_fixture(out),
        "games": games_fixtures(out),
        "geometry": geometry_fixture(out),
        "compose": compose_fixture(out),
    }
    (out / "fixtures.json").write_text(json.dumps(spec, indent=1))
    print(f"fixtures written to {out}")


if __name__ == "__main__":
    main()
