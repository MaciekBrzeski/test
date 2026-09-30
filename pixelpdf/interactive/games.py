"""Built-in games, laid out as ready-to-play A4 pages.

    from pixelpdf.interactive.games import build_game
    build_game("snake").save("snake.pdf")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from ..engine import raster as R
from ..engine.canvas import Canvas, Color
from ..engine.font import draw_text, measure_text
from ..engine.light import glow, vignette
from .builder import Display, InteractiveDocument, InteractivePage

__all__ = ["GAMES", "GameSpec", "add_game_page", "build_game", "draw_led_grid", "game_source"]

_GAME_DIR = Path(__file__).parent / "games"

# Fraction of a cell covered by the ZapfDingbats square at glyph_scale=1.0
# (0.69 em glyph at a font size of 1.2 cells), measured in Chromium.
_GLYPH_FILL = 0.83


@dataclass
class GameSpec:
    title: str
    tagline: str
    script: str
    cols: int
    rows: int
    cell: int
    palette: Sequence[Optional[Color]]
    buttons: Sequence[tuple[str, str]]
    """(key, label) for the on-screen buttons, left to right."""
    help: Sequence[str]
    huds: Sequence[str] = ("score", "best")
    accent: Color = "#ffb347"
    fps: float = 30
    extra: dict = field(default_factory=dict)


GAMES = {
    "snake": GameSpec(
        title="SNAKE", tagline="eat, grow, don't bite yourself",
        script="snake.js", cols=40, rows=30, cell=26,
        palette=[None, "#4a4a66", "#2ecc71", "#b8ffcf", "#ff4d4d", "#ffe66d"],
        buttons=[("w", "^"), ("a", "<"), ("s", "v"), ("d", ">"), (" ", "GO")],
        help=["W A S D: steer", "SPACE: restart after a crash", "P: pause"],
        accent="#2ecc71"),
    "breakout": GameSpec(
        title="BREAKOUT", tagline="clear the wall, keep the ball",
        script="breakout.js", cols=44, rows=36, cell=23,
        palette=[None, "#4a4a66", "#e8e8f0", "#ffe66d",
                 "#ff4d4d", "#ff9f43", "#feca57", "#2ecc71", "#48dbfb", "#ffffff"],
        buttons=[("a", "<"), (" ", "LAUNCH"), ("d", ">")],
        help=["A / D: move the paddle (buttons: hold)", "SPACE: launch the ball", "P: pause"],
        huds=("score", "lives"), accent="#48dbfb"),
    "fireworks": GameSpec(
        title="FIREWORKS", tagline="particle physics, live in a PDF",
        script="fireworks.js", cols=64, rows=48, cell=16,
        palette=[None, "#3a3a52", "#ffffff", "#fff3a0", "#ffb347", "#ff5e3a", "#8a1c2c",
                 "#9ad0ff", "#ffe66d"],
        buttons=[(" ", "LAUNCH"), ("a", "< WIND"), ("d", "WIND >"), ("s", "GRAVITY")],
        help=["SPACE: launch a rocket", "A / D: wind, S: toggle gravity", "P: pause"],
        huds=("count", "wind"), accent="#ff9f43"),
}


def game_source(name: str) -> str:
    return (_GAME_DIR / GAMES[name].script).read_text(encoding="ascii")


def draw_led_grid(canvas: Canvas, d: Display, color: Color) -> None:
    """Paint dim 'off' pixels under the display, matching the live glyphs."""
    side = max(1, round(d.cell * _GLYPH_FILL * d.glyph_scale))
    inset = (d.cell - side) // 2
    for r in range(d.rows):
        for c in range(d.cols):
            R.rect(canvas, d.x + c * d.cell + inset, d.y + r * d.cell + inset, side, side, color)


def build_game(name: str, *, dpi: float = 144, seed: int = 7) -> InteractiveDocument:
    """A one-page A4 PDF with the game, its controls and instructions."""
    if name not in GAMES:
        raise ValueError(f"unknown game {name!r}; choose from {sorted(GAMES)}")
    spec = GAMES[name]
    doc = InteractiveDocument(dpi=dpi, fps=spec.fps, title=f"{spec.title.title()} (pixelpdf)",
                              seed=seed)
    add_game_page(doc, name)
    return doc


def add_game_page(doc: InteractiveDocument, name: str) -> InteractivePage:
    """Append an A4 page with game `name`, its controls and instructions, to `doc`."""
    if name not in GAMES:
        raise ValueError(f"unknown game {name!r}; choose from {sorted(GAMES)}")
    spec = GAMES[name]
    page = doc.new_page(background="#101018")
    c = page.canvas
    W, H = c.width, c.height
    k = W / 1191  # layout was designed at 144 DPI; scale for other resolutions

    def px(v: float) -> int:
        return round(v * k)

    # Title.
    draw_text(c, spec.title, W // 2, px(70), spec.accent, scale=max(1, px(12)), align="center")
    draw_text(c, spec.tagline, W // 2, px(190), "#9a9ab0", scale=max(1, px(3)), align="center")

    # Display with a lit bezel.
    cell = px(spec.cell)
    dw, dh = spec.cols * cell, spec.rows * cell
    x0, y0 = (W - dw) // 2, px(300)
    pad = px(22)
    glow(c, W / 2, y0 + dh / 2, max(dw, dh) * 0.75, spec.accent, intensity=0.18)
    R.rect(c, x0 - pad, y0 - pad, dw + 2 * pad, dh + 2 * pad, "#1c1c2a", radius=px(28))
    R.rect(c, x0 - pad, y0 - pad, dw + 2 * pad, dh + 2 * pad, "#34344a", radius=px(28),
           fill=False, width=max(1, px(3)))
    R.rect(c, x0 - 4, y0 - 4, dw + 8, dh + 8, "#07070c", radius=px(8))
    d = page.display(x0, y0, spec.cols, spec.rows, cell, spec.palette)
    draw_led_grid(c, d, "#15151f")

    # HUD above the display.
    hud_y, hud_h = y0 - pad - px(62), px(44)
    page.hud(spec.huds[0], x0, hud_y, dw // 2, hud_h, color="#e8e8f0")
    page.hud(spec.huds[1], x0 + dw // 2, hud_y, dw // 2, hud_h, color="#9a9ab0", align="right")

    # Controls: key capture box, then buttons.
    cy = y0 + dh + pad + px(50)
    box_w, box_h = px(330), px(70)
    draw_text(c, "CLICK BOX, THEN TYPE", x0, cy, "#9a9ab0", scale=max(1, px(2)))
    R.rect(c, x0 - 3, cy + px(34) - 3, box_w + 6, box_h + 6, spec.accent, radius=px(6))
    page.key_capture(x0, cy + px(34), box_w, box_h)

    bx = x0 + box_w + px(40)
    draw_text(c, "OR PRESS AND HOLD", bx, cy, "#9a9ab0", scale=max(1, px(2)))
    gap = px(14)
    bw = (x0 + dw - bx - gap * (len(spec.buttons) - 1)) // len(spec.buttons)
    for i, (key, label) in enumerate(spec.buttons):
        page.button(key, bx + i * (bw + gap), cy + px(34), bw, box_h, label=label)

    # Help and compatibility notes.
    hy = cy + px(150)
    for line in spec.help:
        draw_text(c, line, x0, hy, "#e8e8f0", scale=max(1, px(3)))
        hy += px(40)
    notes = ["Runs in Chrome, Edge and Adobe Acrobat/Reader (JavaScript enabled).",
             "Other viewers show the empty screen: they don't run PDF scripts."]
    ny = H - px(60) - len(notes) * px(30)
    for line in notes:
        draw_text(c, line, W // 2, ny, "#6b6b80", scale=max(1, px(2)), align="center")
        ny += px(30)
    vignette(c, strength=0.35)

    page.set_game(game_source(name))
    return page
