"""Built-in 5x7 bitmap font and text drawing.

Glyphs are 5 px wide with a 7 px cap height and 2 px descenders (cell
5x9). Text is scaled by whole-pixel factors, so it always stays crisp and
pixel-exact. Per-character offsets and colors make animated effects
possible (see `text_fx`).
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Union

import numpy as np

from .canvas import Canvas

__all__ = ["BitmapFont", "DEFAULT_FONT", "draw_text", "measure_text"]

# Rows top to bottom, '#' = ink. Seven rows (cap height) plus up to two
# descender rows.
_GLYPHS = {
    " ": ".....|.....|.....|.....|.....|.....|.....",
    "!": "..#..|..#..|..#..|..#..|..#..|.....|..#..",
    '"': ".#.#.|.#.#.|.....|.....|.....|.....|.....",
    "#": ".#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.",
    "$": "..#..|.####|#.#..|.###.|..#.#|####.|..#..",
    "%": "##...|##..#|...#.|..#..|.#...|#..##|...##",
    "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#",
    "'": "..#..|..#..|.#...|.....|.....|.....|.....",
    "(": "...#.|..#..|.#...|.#...|.#...|..#..|...#.",
    ")": ".#...|..#..|...#.|...#.|...#.|..#..|.#...",
    "*": ".....|..#..|#.#.#|.###.|#.#.#|..#..|.....",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....",
    ",": ".....|.....|.....|.....|.....|..##.|...#.|..#..",
    "-": ".....|.....|.....|#####|.....|.....|.....",
    ".": ".....|.....|.....|.....|.....|.##..|.##..",
    "/": ".....|....#|...#.|..#..|.#...|#....|.....",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.",
    "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####",
    "3": "#####|...#.|..#..|...#.|....#|#...#|.###.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.",
    "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.",
    "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
    ":": ".....|.##..|.##..|.....|.##..|.##..|.....",
    ";": ".....|.##..|.##..|.....|.##..|..#..|.#...",
    "<": "...#.|..#..|.#...|#....|.#...|..#..|...#.",
    "=": ".....|.....|#####|.....|#####|.....|.....",
    ">": ".#...|..#..|...#.|....#|...#.|..#..|.#...",
    "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "@": ".###.|#...#|....#|.##.#|#.#.#|#.#.#|.###.",
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#",
    "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.",
    "D": "###..|#..#.|#...#|#...#|#...#|#..#.|###..",
    "E": "#####|#....|#....|####.|#....|#....|#####",
    "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####",
    "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": ".###.|..#..|..#..|..#..|..#..|..#..|.###.",
    "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#",
    "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "[": ".###.|.#...|.#...|.#...|.#...|.#...|.###.",
    "\\": ".....|#....|.#...|..#..|...#.|....#|.....",
    "]": ".###.|...#.|...#.|...#.|...#.|...#.|.###.",
    "^": "..#..|.#.#.|#...#|.....|.....|.....|.....",
    "_": ".....|.....|.....|.....|.....|.....|.....|#####",
    "`": ".#...|..#..|.....|.....|.....|.....|.....",
    "a": ".....|.....|.###.|....#|.####|#...#|.####",
    "b": "#....|#....|#.##.|##..#|#...#|#...#|####.",
    "c": ".....|.....|.###.|#....|#....|#...#|.###.",
    "d": "....#|....#|.##.#|#..##|#...#|#...#|.####",
    "e": ".....|.....|.###.|#...#|#####|#....|.###.",
    "f": "..##.|.#..#|.#...|###..|.#...|.#...|.#...",
    "g": ".....|.....|.####|#...#|#...#|#...#|.####|....#|.###.",
    "h": "#....|#....|#.##.|##..#|#...#|#...#|#...#",
    "i": "..#..|.....|.##..|..#..|..#..|..#..|.###.",
    "j": "...#.|.....|..##.|...#.|...#.|...#.|...#.|#..#.|.##..",
    "k": "#....|#....|#..#.|#.#..|##...|#.#..|#..#.",
    "l": ".##..|..#..|..#..|..#..|..#..|..#..|.###.",
    "m": ".....|.....|##.#.|#.#.#|#.#.#|#.#.#|#.#.#",
    "n": ".....|.....|#.##.|##..#|#...#|#...#|#...#",
    "o": ".....|.....|.###.|#...#|#...#|#...#|.###.",
    "p": ".....|.....|####.|#...#|#...#|#...#|####.|#....|#....",
    "q": ".....|.....|.####|#...#|#...#|#...#|.####|....#|....#",
    "r": ".....|.....|#.##.|##..#|#....|#....|#....",
    "s": ".....|.....|.###.|#....|.###.|....#|####.",
    "t": ".#...|.#...|###..|.#...|.#...|.#..#|..##.",
    "u": ".....|.....|#...#|#...#|#...#|#..##|.##.#",
    "v": ".....|.....|#...#|#...#|#...#|.#.#.|..#..",
    "w": ".....|.....|#...#|#...#|#.#.#|#.#.#|.#.#.",
    "x": ".....|.....|#...#|.#.#.|..#..|.#.#.|#...#",
    "y": ".....|.....|#...#|#...#|#...#|#...#|.####|....#|.###.",
    "z": ".....|.....|#####|...#.|..#..|.#...|#####",
    "{": "...#.|..#..|..#..|.#...|..#..|..#..|...#.",
    "|": "..#..|..#..|..#..|..#..|..#..|..#..|..#..",
    "}": ".#...|..#..|..#..|...#.|..#..|..#..|.#...",
    "~": ".....|.....|.#...|#.#.#|...#.|.....|.....",
}
_MISSING = "#####|#...#|#...#|#...#|#...#|#...#|#####"


class BitmapFont:
    """A monospaced bitmap font built from row strings."""

    def __init__(self, glyphs: dict[str, str], width: int = 5, cap_height: int = 7,
                 descent: int = 2, missing: str = _MISSING):
        self.glyph_width = width
        self.cap_height = cap_height
        self.cell_height = cap_height + descent
        self._glyphs = {ch: self._parse(rows) for ch, rows in glyphs.items()}
        self._missing = self._parse(missing)

    def _parse(self, rows: str) -> np.ndarray:
        lines = rows.split("|")
        if len(lines) > self.cell_height or any(len(r) != self.glyph_width for r in lines):
            raise ValueError(f"malformed glyph {rows!r}")
        cell = np.zeros((self.cell_height, self.glyph_width), dtype=bool)
        for y, row in enumerate(lines):
            cell[y] = [ch == "#" for ch in row]
        return cell

    def glyph(self, ch: str) -> np.ndarray:
        """(cell_height, width) bool mask for `ch`; a box for unknown characters."""
        return self._glyphs.get(ch, self._missing)

    def has_glyph(self, ch: str) -> bool:
        return ch in self._glyphs

    def advance(self, scale: int = 1, spacing: int = 1) -> int:
        return (self.glyph_width + spacing) * scale

    def line_height(self, scale: int = 1, leading: int = 2) -> int:
        return (self.cell_height + leading) * scale


DEFAULT_FONT = BitmapFont(_GLYPHS)


def measure_text(text: str, scale: int = 1, font: BitmapFont = DEFAULT_FONT,
                 spacing: int = 1, leading: int = 2) -> tuple[int, int]:
    """(width, height) in pixels of the text's bounding box, including descenders."""
    lines = text.split("\n")
    longest = max(len(line) for line in lines)
    width = max(longest * font.advance(scale, spacing) - spacing * scale, 0)
    height = (len(lines) - 1) * font.line_height(scale, leading) + font.cell_height * scale
    return width, height


Offsets = Union[Sequence[tuple[float, float]], Callable[[int], tuple[float, float]]]
Colors = Union[Sequence, Callable[[int], object]]


def draw_text(canvas: Canvas, text: str, x: int, y: int, color=0, *, scale: int = 1,
              font: BitmapFont = DEFAULT_FONT, spacing: int = 1, leading: int = 2,
              align: str = "left", offsets: Optional[Offsets] = None,
              colors: Optional[Colors] = None, mode: str = "normal",
              opacity: float = 1.0) -> tuple[int, int]:
    """Draw `text` with its top-left corner at (x, y); returns the (width, height) drawn.

    `align` is left, center or right; x is then the left edge, centre or
    right edge. `offsets` and `colors` give per-character (dx, dy) shifts
    and colors, as sequences or as functions of the character index (which
    counts every character, newlines excluded). Offsets are rounded to
    whole pixels so glyphs stay crisp.
    """
    if align not in ("left", "center", "right"):
        raise ValueError(f"align must be left, center or right, got {align!r}")
    advance = font.advance(scale, spacing)
    index = 0
    for row, line_text in enumerate(text.split("\n")):
        line_width, _ = measure_text(line_text or " ", scale, font, spacing, leading)
        if align == "center":
            lx = x - line_width // 2
        elif align == "right":
            lx = x - line_width
        else:
            lx = x
        ly = y + row * font.line_height(scale, leading)
        for col, ch in enumerate(line_text):
            if ch != " ":
                mask = font.glyph(ch)
                if scale > 1:
                    mask = mask.repeat(scale, axis=0).repeat(scale, axis=1)
                dx, dy = _pick(offsets, index, (0, 0))
                canvas.blend(lx + col * advance + round(dx), ly + round(dy), mask,
                             _pick(colors, index, color), mode=mode, opacity=opacity)
            index += 1
    return measure_text(text, scale, font, spacing, leading)


def _pick(source, index: int, default):
    if source is None:
        return default
    if callable(source):
        return source(index)
    return source[index] if index < len(source) else default
