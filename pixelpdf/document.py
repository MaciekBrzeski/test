"""High-level API: a document made of pixel-exact pages.

    doc = Document()               # 144 DPI by default
    page = doc.new_page()          # A4 canvas, 1191x1684 px
    page.canvas.set_pixel(10, 10, "#ff0000")
    doc.save("out.pdf")

Each page's canvas is embedded losslessly as one image covering the whole
page. The page size is derived from the pixel size (1 px = 72/dpi pt), so
pixels map onto the page exactly; for A4 this differs from the nominal
210x297 mm by under 0.3 mm.

Prefer a DPI of 72 * 2**k (72, 144, 288, ...). Then 1 px is a binary
fraction of a point, page sizes are exact in the 32-bit floats viewers
use, and a render at zoom dpi/72 is pixel-for-pixel identical to the
canvas. Other DPIs (e.g. 150, 300) still embed exact pixel data, but
viewers may round the page to one device pixel more or fewer and
resample the image slightly.
"""

from __future__ import annotations

import io
import os
from typing import BinaryIO, Union

from .engine.canvas import Canvas, Color, a4_size
from .pdf.image import encode_image
from .pdf.objects import Name, Stream, serialize
from .pdf.writer import PdfWriter

__all__ = ["Document", "Page"]

POINTS_PER_INCH = 72.0


class Page:
    def __init__(self, canvas: Canvas, dpi: float):
        self.canvas = canvas
        self.dpi = dpi

    @property
    def size_points(self) -> tuple[float, float]:
        scale = POINTS_PER_INCH / self.dpi
        return self.canvas.width * scale, self.canvas.height * scale


class Document:
    def __init__(self, dpi: float = 144, mode: str = "RGB", title: str | None = None,
                 compression: int = 6):
        if dpi <= 0:
            raise ValueError("dpi must be positive")
        self.dpi = dpi
        self.mode = mode
        self.title = title
        self.compression = compression
        self.pages: list[Page] = []

    def new_page(self, background: Color = 255, size: tuple[int, int] | None = None) -> Page:
        """Append a page. `size` is (width, height) in pixels; defaults to A4."""
        width, height = size or a4_size(self.dpi)
        page = Page(Canvas(width, height, self.mode, background), self.dpi)
        self.pages.append(page)
        return page

    def add_canvas(self, canvas: Canvas) -> Page:
        """Append a page showing an existing canvas."""
        page = Page(canvas, self.dpi)
        self.pages.append(page)
        return page

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
        w = PdfWriter()
        catalog = w.reserve()
        pages_root = w.reserve()

        kids = []
        for page in self.pages:
            width_pt, height_pt = page.size_points
            image = w.add(encode_image(page.canvas.pixels, level=self.compression))
            content = b"q %s 0 0 %s 0 0 cm /Im0 Do Q" % (
                serialize(width_pt), serialize(height_pt))
            kids.append(w.add({
                "Type": Name("Page"),
                "Parent": pages_root,
                "MediaBox": [0, 0, width_pt, height_pt],
                "Resources": {"XObject": {"Im0": image}},
                "Contents": w.add(Stream({}, content)),
            }))

        w.set(pages_root, {"Type": Name("Pages"), "Kids": kids, "Count": len(kids)})
        w.set(catalog, {"Type": Name("Catalog"), "Pages": pages_root})
        info = {"Producer": "pixelpdf"}
        if self.title:
            info["Title"] = self.title
        w.write(fp, catalog, w.add(info))

