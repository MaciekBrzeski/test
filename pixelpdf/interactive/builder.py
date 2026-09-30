"""Build interactive PDF pages: static artwork plus a live, scriptable display.

The page background is an ordinary pixel-exact canvas. On top of it sit
form fields that the embedded JavaScript runtime drives:

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
    doc.set_game(js_source)
    doc.save("game.pdf")
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Optional, Sequence, Union

from ..engine.canvas import Canvas, Color, a4_size, parse_color
from ..pdf.image import encode_image
from ..pdf.objects import Name, Ref, Stream, serialize
from ..pdf.writer import PdfWriter

__all__ = ["InteractiveDocument", "InteractivePage", "Display", "GLYPHS", "RUNTIME_JS"]

RUNTIME_JS = (Path(__file__).parent / "runtime.js").read_text(encoding="ascii")

# ZapfDingbats characters: n = black square, l = black circle, u = black diamond.
GLYPHS = {"square": "n", "dot": "l", "diamond": "u"}

_READ_ONLY = 1
_DO_NOT_SPELL_CHECK = 1 << 22
_DO_NOT_SCROLL = 1 << 23
_COMB = 1 << 24
_PUSH_BUTTON = 1 << 16
_PRINT = 4  # annotation flag: show when printing too


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
        self.key_field: Optional[str] = None

    def display(self, x: int, y: int, cols: int, rows: int, cell: int,
                palette: Sequence[Optional[Color]], glyph: str = "square",
                glyph_scale: float = 1.0) -> Display:
        """Add the live pixel display (one per document)."""
        if self.doc._display_page is not None:
            raise ValueError("an interactive document has exactly one display")
        if glyph not in GLYPHS:
            raise ValueError(f"glyph must be one of {sorted(GLYPHS)}")
        if len(palette) < 2:
            raise ValueError("palette needs index 0 (transparent) and at least one colour")
        spec = Display(x, y, cols, rows, cell, list(palette), glyph, glyph_scale)
        self.display_spec = spec
        self.doc._display_page = self
        return spec

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
        if self.key_field is not None:
            raise ValueError("a page has one key capture field")
        self.key_field = "keys"
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
        self._display_page: Optional[InteractivePage] = None
        self.game_js: Optional[str] = None

    def new_page(self, background: Color = 255, size: Optional[tuple[int, int]] = None,
                 mode: str = "RGB") -> InteractivePage:
        width, height = size or a4_size(self.dpi)
        page = InteractivePage(self, Canvas(width, height, mode, background))
        self.pages.append(page)
        return page

    def set_game(self, source: str) -> None:
        """JavaScript that calls PX.run({init: ..., update: ...})."""
        self.game_js = source

    def script(self) -> str:
        """The complete document script: config, runtime, game, start."""
        page = self._display_page
        if page is None or self.game_js is None:
            raise ValueError("add a display and set a game before saving")
        d = page.display_spec
        config = {
            "cols": d.cols, "rows": d.rows, "colors": len(d.palette), "prefix": "px",
            "glyph": GLYPHS[d.glyph], "fps": self.fps, "seed": self.seed,
            "holdMs": self.hold_ms, "pauseKey": self.pause_key, "keyField": page.key_field,
        }
        return ("var PX_CONFIG = " + json.dumps(config) + ";\n" + RUNTIME_JS + "\n"
                + self.game_js + "\nPX.start();\n")

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
        if not self.pages:
            raise ValueError("document has no pages")
        script = self.script()
        w = PdfWriter()
        catalog, pages_root = w.reserve(), w.reserve()
        fonts = {
            "Cour": w.add(_font("Courier-Bold")),
            "Helv": w.add(_font("Helvetica-Bold")),
            "ZaDb": w.add({"Type": Name("Font"), "Subtype": Name("Type1"),
                           "BaseFont": Name("ZapfDingbats")}),
        }
        kids, all_fields = [], []
        for page in self.pages:
            page_ref = w.reserve()
            annots = [w.add(a) for a in self._annotations(page, page_ref)]
            all_fields.extend(annots)
            height = page.canvas.height
            s = 72 / self.dpi
            content = b"q %s 0 0 %s 0 0 cm /Im0 Do Q" % (
                serialize(page.canvas.width * s), serialize(height * s))
            w.set(page_ref, {
                "Type": Name("Page"), "Parent": pages_root,
                "MediaBox": [0, 0, page.canvas.width * s, height * s],
                "Resources": {"XObject": {"Im0": w.add(encode_image(page.canvas.pixels))}},
                "Contents": w.add(Stream({}, content)),
                "Annots": annots,
            })
            kids.append(page_ref)
        w.set(pages_root, {"Type": Name("Pages"), "Kids": kids, "Count": len(kids)})
        w.set(catalog, {
            "Type": Name("Catalog"), "Pages": pages_root,
            "AcroForm": {"Fields": all_fields, "DR": {"Font": fonts}, "DA": "/Helv 12 Tf 0 g"},
            "OpenAction": {"S": Name("JavaScript"), "JS": script},
        })
        info = {"Producer": "pixelpdf"}
        if self.title:
            info["Title"] = self.title
        w.write(fp, catalog, w.add(info))

    def _rect(self, page: InteractivePage, x: float, y: float, w: float, h: float) -> list[float]:
        s = 72 / self.dpi
        top = page.canvas.height
        return [x * s, (top - y - h) * s, (x + w) * s, (top - y) * s]

    def _annotations(self, page: InteractivePage, page_ref: Ref) -> list[dict]:
        s = 72 / self.dpi
        out = []
        d = page.display_spec
        if d is not None:
            size = d.cell * s * 1.2 * d.glyph_scale
            for r in range(d.rows):
                rect = self._rect(page, d.x, d.y + r * d.cell, d.width, d.cell)
                for k in range(1, len(d.palette)):
                    out.append(_widget(page_ref, f"px{r}_{k}", rect, {
                        "FT": Name("Tx"), "V": "", "MaxLen": d.cols,
                        "Ff": _READ_ONLY | _COMB | _DO_NOT_SCROLL | _DO_NOT_SPELL_CHECK,
                        "DA": _da("ZaDb", round(size, 2), d.palette[k]),
                    }))
        for f in page.fields:
            rect = self._rect(page, *f.rect)
            spec = f.spec
            if f.kind == "hud":
                size = spec["size"] or round(f.rect[3] * s * 0.7, 1)
                font = "Cour" if spec["font"] == "mono" else "Helv"
                out.append(_widget(page_ref, f.name, rect, {
                    "FT": Name("Tx"), "V": spec["value"], "Ff": _READ_ONLY | _DO_NOT_SCROLL,
                    "DA": _da(font, size, spec["color"]),
                    "Q": {"left": 0, "center": 1, "right": 2}[spec["align"]],
                }))
            elif f.kind == "button":
                key = json.dumps(spec["key"])
                out.append(_widget(page_ref, f.name, rect, {
                    "FT": Name("Btn"), "Ff": _PUSH_BUTTON,
                    "DA": _da("Helv", round(f.rect[3] * s * 0.5, 1), spec["text_color"]),
                    "MK": {"BG": _rgb(spec["color"]), "CA": spec["label"]},
                    "AA": {"D": _js(f"PX._down({key});"), "U": _js(f"PX._up({key});"),
                           "X": _js(f"PX._up({key});")},
                }))
            elif f.kind == "keys":
                out.append(_widget(page_ref, f.name, rect, {
                    "FT": Name("Tx"), "V": "", "Ff": _DO_NOT_SCROLL | _DO_NOT_SPELL_CHECK,
                    "DA": _da("Cour", round(f.rect[3] * s * 0.5, 1), spec["text_color"]),
                    "MK": {"BG": _rgb(spec["color"])},
                    "AA": {"K": _js("if (!event.willCommit) PX._key(event.change); event.change = '';")},
                }))
        return out


def _font(base: str) -> dict:
    return {"Type": Name("Font"), "Subtype": Name("Type1"), "BaseFont": Name(base),
            "Encoding": Name("WinAnsiEncoding")}


def _js(source: str) -> dict:
    return {"S": Name("JavaScript"), "JS": source}


def _widget(page_ref: Ref, name: str, rect: list[float], extra: dict) -> dict:
    return {"Type": Name("Annot"), "Subtype": Name("Widget"), "T": name, "Rect": rect,
            "P": page_ref, "F": _PRINT, **extra}
