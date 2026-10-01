"""Build interactive PDF pages: static artwork plus a live, scriptable display.

The page background is an ordinary pixel-exact canvas. On top of it sit
form fields that the embedded JavaScript runtime drives. Each page with a
display runs its own game, and only while that page is in view, so one
document (or a Composer) can hold several games:

- a *display*: `rows x (colors - 1)` read-only comb text fields, each row
  holding glyphs (squares by default) in one palette colour,
- *HUD* text fields (score, lives, ...),
- push *buttons* that act like held keys,
- a *key capture* field: click it and type to send keys.

Geometry is given in canvas pixels, like everything else in pixelpdf.

    doc = InteractiveDocument(fps=30)
    page = doc.new_page(background="#101018")
    page.display(x=60, y=200, cols=40, rows=30, cell=26, palette=[None, "#ff0000", ...])
    page.hud("score", x=60, y=120, w=300, h=40)
    page.key_capture(x=60, y=1100, w=300, h=50)
    page.button("a", x=400, y=1100, w=80, h=60, label="<")
    page.set_game(js_source)          # or doc.set_game(...) for the only display
    doc.save("game.pdf")
"""

from __future__ import annotations

import io
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional, Sequence, Union

from ..engine.canvas import Canvas, Color, a4_size, parse_color
from ..pdf.objects import Name, Ref, Stream, serialize
from ..pdf.pages import PageSink, image_page

__all__ = ["InteractiveDocument", "InteractivePage", "Display", "GLYPHS", "UNICODE_GLYPHS",
           "RUNTIME_JS"]

RUNTIME_JS = (Path(__file__).parent / "runtime.js").read_text(encoding="ascii")

# ZapfDingbats characters: n = black square, l = black circle, u = black diamond.
GLYPHS = {"square": "n", "dot": "l", "diamond": "u"}
# The same shapes in Unicode, for viewers that draw fields with web fonts (pdf.js).
UNICODE_GLYPHS = {"square": "\u25a0", "dot": "\u25cf", "diamond": "\u25c6"}

_READ_ONLY = 1
_DO_NOT_SPELL_CHECK = 1 << 22
_DO_NOT_SCROLL = 1 << 23
_COMB = 1 << 24
_PUSH_BUTTON = 1 << 16
_PRINT = 4  # annotation flag: show when printing too

# Helvetica-Bold advance widths (1/1000 em) from the standard AFM metrics,
# for centring button labels. Characters not listed use 611.
_HELV_BOLD = {
    " ": 278, "!": 333, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 333,
    "<": 584, "=": 584, ">": 584, "?": 611, "^": 584, "_": 556, "|": 280,
    **{d: 556 for d in "0123456789"},
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778, "H": 722,
    "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722, "O": 778, "P": 667,
    "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944, "X": 667,
    "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611, "h": 611,
    "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611, "o": 611, "p": 611,
    "q": 611, "r": 389, "s": 556, "t": 333, "u": 611, "v": 556, "w": 778, "x": 556,
    "y": 556, "z": 500,
}


def _label_width(label: str, font_size: float) -> float:
    return sum(_HELV_BOLD.get(ch, 611) for ch in label) * font_size / 1000


def _rgb(color, channels: int = 3) -> list[float]:
    return [round(v / 255, 4) for v in parse_color(color, channels)]


def _da(font: str, size: float, color) -> str:
    r, g, b = _rgb(color)
    return f"/{font} {size:g} Tf {r:g} {g:g} {b:g} rg"


@dataclass
class Display:
    x: int
    y: int
    cols: int
    rows: int
    cell: int
    palette: Sequence[Optional[Color]]
    """Colour per index; index 0 is transparent (use None)."""
    glyph: str = "square"
    glyph_scale: float = 1.0
    """Font size relative to the cell; 1.0 leaves a small gap between cells."""

    @property
    def width(self) -> int:
        return self.cols * self.cell

    @property
    def height(self) -> int:
        return self.rows * self.cell


@dataclass
class _Field:
    kind: str
    name: str
    rect: tuple[int, int, int, int]  # canvas px: x, y, w, h
    spec: dict = field(default_factory=dict)


class InteractivePage:
    def __init__(self, doc: "InteractiveDocument", canvas: Canvas):
        self.doc = doc
        self.canvas = canvas
        self.fields: list[_Field] = []
        self.display_spec: Optional[Display] = None
        self.game_js: Optional[str] = None
        self.has_key_capture = False

    def display(self, x: int, y: int, cols: int, rows: int, cell: int,
                palette: Sequence[Optional[Color]], glyph: str = "square",
                glyph_scale: float = 1.0) -> Display:
        """Add this page's live pixel display (one per page)."""
        if self.display_spec is not None:
            raise ValueError("a page has one display")
        if glyph not in GLYPHS:
            raise ValueError(f"glyph must be one of {sorted(GLYPHS)}")
        if len(palette) < 2:
            raise ValueError("palette needs index 0 (transparent) and at least one colour")
        self.display_spec = Display(x, y, cols, rows, cell, list(palette), glyph, glyph_scale)
        return self.display_spec

    def set_game(self, source: str) -> None:
        """JavaScript for this page's display; it calls PX.run({init, update})."""
        self.game_js = source

    def hud(self, name: str, x: int, y: int, w: int, h: int, *, value: str = "",
            size: Optional[float] = None, color: Color = "#ffffff", align: str = "left",
            font: str = "mono") -> None:
        """A read-only text field the game sets with px.hud(name, text)."""
        self.fields.append(_Field("hud", f"hud_{name}", (x, y, w, h), dict(
            value=value, size=size, color=color, align=align, font=font)))

    def button(self, key: str, x: int, y: int, w: int, h: int, *, label: str = "",
               color: Color = "#3a3a4a", text_color: Color = "#ffffff") -> None:
        """A push button that holds `key` down while pressed."""
        if len(key) != 1:
            raise ValueError("button keys are single characters, as typed")
        n = sum(f.kind == "button" for f in self.fields)
        self.fields.append(_Field("button", f"btn_{n}", (x, y, w, h), dict(
            key=key.lower(), label=label, color=color, text_color=text_color)))

    def key_capture(self, x: int, y: int, w: int, h: int, *, color: Color = "#fff8d0",
                    text_color: Color = "#000000") -> None:
        """The field players click, then type into, to send keys to the game."""
        if self.has_key_capture:
            raise ValueError("a page has one key capture field")
        self.has_key_capture = True
        self.fields.append(_Field("keys", "keys", (x, y, w, h), dict(
            color=color, text_color=text_color)))


class InteractiveDocument:
    def __init__(self, dpi: float = 144, fps: float = 30, *, title: Optional[str] = None,
                 seed: int = 1, hold_ms: int = 150, pause_key: str = "p"):
        self.dpi = dpi
        self.fps = fps
        self.title = title
        self.seed = seed
        self.hold_ms = hold_ms
        self.pause_key = pause_key
        self.pages: list[InteractivePage] = []

    def new_page(self, background: Color = 255, size: Optional[tuple[int, int]] = None,
                 mode: str = "RGB") -> InteractivePage:
        width, height = size or a4_size(self.dpi)
        page = InteractivePage(self, Canvas(width, height, mode, background))
        self.pages.append(page)
        return page

    def set_game(self, source: str) -> None:
        """Set the game of the document's only display page."""
        displays = [p for p in self.pages if p.display_spec is not None]
        if len(displays) != 1:
            raise ValueError("set_game needs exactly one display page; use page.set_game")
        displays[0].set_game(source)

    def script(self) -> str:
        """The complete open-action script this document would carry on its own."""
        sink = PageSink()
        self.emit(sink)
        return "\n".join(sink.scripts.values())

    # -- output --------------------------------------------------------------

    def save(self, target: Union[str, os.PathLike, BinaryIO]) -> None:
        if isinstance(target, (str, os.PathLike)):
            with open(target, "wb") as fp:
                self._write(fp)
        else:
            self._write(target)

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        self._write(buf)
        return buf.getvalue()

    def _write(self, fp: BinaryIO) -> None:
        sink = PageSink()
        self.emit(sink)
        sink.write(fp, title=self.title)

    def emit(self, sink: PageSink) -> list[int]:
        """Append this document's pages, fields and scripts to `sink`; returns page indices."""
        if not self.pages:
            raise ValueError("document has no pages")
        for page in self.pages:
            if page.display_spec is not None and page.game_js is None:
                raise ValueError("every display needs a game: call page.set_game(...)")
        if not any(p.display_spec is not None for p in self.pages):
            raise ValueError("add a display (page.display(...)) before saving")
        sink.add_script("pixelpdf-runtime", RUNTIME_JS)
        indices = []
        for page in self.pages:
            index = len(sink)
            game_id = f"g{sum(k.startswith('game:') for k in sink.scripts)}"
            page_ref = image_page(sink, page.canvas.pixels, self.dpi)
            annots = [sink.writer.add(a) for a in self._annotations(sink, page, page_ref, game_id)]
            sink.page(index)[1]["Annots"] = annots
            sink.fields.extend(annots)
            if page.display_spec is not None:
                sink.add_script(f"game:{game_id}", self._instance_script(page, game_id, index))
            indices.append(index)
        return indices

    @staticmethod
    def _button_appearance(sink: PageSink, rect: list[float], spec: dict, font_size: float) -> Ref:
        """Form XObject: filled background with the label centred in Helvetica-Bold."""
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        label = spec["label"]
        text_w = _label_width(label, font_size)
        if text_w > w * 0.9:  # shrink labels that would not fit
            font_size = math.floor(font_size * w * 0.9 / text_w * 100) / 100
            text_w = _label_width(label, font_size)
        r, g, b = _rgb(spec["color"])
        tr, tg, tb = _rgb(spec["text_color"])
        ops = (f"{r:g} {g:g} {b:g} rg 0 0 {w:.2f} {h:.2f} re f "
               f"BT /Helv {font_size:g} Tf {tr:g} {tg:g} {tb:g} rg "
               f"{(w - text_w) / 2:.2f} {(h - font_size * 0.7) / 2:.2f} Td ")
        content = ops.encode("ascii") + serialize(label) + b" Tj ET"
        return sink.writer.add(Stream({
            "Type": Name("XObject"), "Subtype": Name("Form"), "BBox": [0, 0, w, h],
            "Resources": {"Font": {"Helv": sink.form_fonts()["Helv"]}},
        }, content))

    def _instance_script(self, page: InteractivePage, game_id: str, index: int) -> str:
        d = page.display_spec
        config = {
            "id": game_id, "page": index, "cols": d.cols, "rows": d.rows,
            "colors": len(d.palette), "prefix": f"{game_id}_px", "glyph": GLYPHS[d.glyph],
            "unicodeGlyph": UNICODE_GLYPHS[d.glyph],
            "fps": self.fps, "seed": self.seed, "holdMs": self.hold_ms,
            "pauseKey": self.pause_key,
            "keyField": f"{game_id}_keys" if page.has_key_capture else None,
        }
        return ("(function () {\nvar PX = PXRuntime(" + json.dumps(config) + ");\n"
                + page.game_js + "\nPX.start();\n})();")

    def _rect(self, page: InteractivePage, x: float, y: float, w: float, h: float) -> list[float]:
        s = 72 / self.dpi
        top = page.canvas.height
        return [x * s, (top - y - h) * s, (x + w) * s, (top - y) * s]

    def _annotations(self, sink: PageSink, page: InteractivePage, page_ref: Ref,
                     game_id: str) -> list[dict]:
        s = 72 / self.dpi
        out = []
        d = page.display_spec
        runtime = f'PXR["{game_id}"]'
        if d is not None:
            size = d.cell * s * 1.2 * d.glyph_scale
            for r in range(d.rows):
                rect = self._rect(page, d.x, d.y + r * d.cell, d.width, d.cell)
                for k in range(1, len(d.palette)):
                    out.append(_widget(page_ref, f"{game_id}_px{r}_{k}", rect, {
                        "FT": Name("Tx"), "V": "", "MaxLen": d.cols,
                        "Ff": _READ_ONLY | _COMB | _DO_NOT_SCROLL | _DO_NOT_SPELL_CHECK,
                        "DA": _da("ZaDb", round(size, 2), d.palette[k]),
                    }))
        for f in page.fields:
            rect = self._rect(page, *f.rect)
            spec = f.spec
            name = f"{game_id}_{f.name}"
            if f.kind == "hud":
                size = spec["size"] or round(f.rect[3] * s * 0.7, 1)
                font = "Cour" if spec["font"] == "mono" else "Helv"
                out.append(_widget(page_ref, name, rect, {
                    "FT": Name("Tx"), "V": spec["value"], "Ff": _READ_ONLY | _DO_NOT_SCROLL,
                    "DA": _da(font, size, spec["color"]),
                    "Q": {"left": 0, "center": 1, "right": 2}[spec["align"]],
                }))
            elif f.kind == "button":
                key = json.dumps(spec["key"])
                font_size = round(f.rect[3] * s * 0.5, 1)
                out.append(_widget(page_ref, name, rect, {
                    "FT": Name("Btn"), "Ff": _PUSH_BUTTON,
                    "DA": _da("Helv", font_size, spec["text_color"]),
                    "MK": {"BG": _rgb(spec["color"]), "CA": spec["label"]},
                    # Explicit appearance: viewers that don't generate one from
                    # MK (pdf.js, Preview, printing) still show the button.
                    "AP": {"N": self._button_appearance(sink, rect, spec, font_size)},
                    "AA": {"D": _js(f"{runtime}._down({key});"), "U": _js(f"{runtime}._up({key});"),
                           "X": _js(f"{runtime}._up({key});")},
                }))
            elif f.kind == "keys":
                out.append(_widget(page_ref, name, rect, {
                    "FT": Name("Tx"), "V": "", "Ff": _DO_NOT_SCROLL | _DO_NOT_SPELL_CHECK,
                    "DA": _da("Cour", round(f.rect[3] * s * 0.5, 1), spec["text_color"]),
                    "MK": {"BG": _rgb(spec["color"])},
                    "AA": {"K": _js(f"if (!event.willCommit) {runtime}._key(event.change); "
                                    "event.change = '';")},
                }))
        return out


def _js(source: str) -> dict:
    return {"S": Name("JavaScript"), "JS": source}


def _widget(page_ref: Ref, name: str, rect: list[float], extra: dict) -> dict:
    return {"Type": Name("Annot"), "Subtype": Name("Widget"), "T": name, "Rect": rect,
            "P": page_ref, "F": _PRINT, **extra}
