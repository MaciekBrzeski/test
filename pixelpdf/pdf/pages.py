"""Page collection shared by every backend.

A `PageSink` gathers, for one output file: pages (in order), form fields,
document scripts, link annotations and bookmarks. Static documents,
flipbooks and interactive documents all write through a sink, which is
how `Composer` mixes them in a single PDF.
"""

from __future__ import annotations

from typing import Any, BinaryIO, Optional

import numpy as np

from .image import encode_image
from .objects import Name, Ref, Stream, serialize
from .writer import PdfWriter

__all__ = ["PageSink", "image_page"]


class PageSink:
    def __init__(self) -> None:
        self.writer = PdfWriter()
        self.catalog = self.writer.reserve()
        self.pages_root = self.writer.reserve()
        self.info = self.writer.reserve()
        self.pages: list[tuple[Ref, dict]] = []
        self.fields: list[Ref] = []
        self.scripts: dict[str, str] = {}  # key -> source, run in order at open
        self.bookmarks: list[tuple[str, int]] = []
        self._fonts: Optional[dict[str, Ref]] = None

    def __len__(self) -> int:
        return len(self.pages)

    def add_page(self, page: dict) -> Ref:
        """Append a page dictionary; it is written (and may still be amended) at save."""
        ref = self.writer.reserve()
        page = dict(page, Type=Name("Page"), Parent=self.pages_root)
        self.pages.append((ref, page))
        return ref

    def page(self, index: int) -> tuple[Ref, dict]:
        return self.pages[index]

    def add_link(self, index: int, rect: list[float], target: int) -> None:
        """Clickable area on page `index` (rect in points) jumping to page `target`."""
        ref, page = self.pages[index]
        target_ref = self.pages[target][0]
        page.setdefault("Annots", []).append(self.writer.add({
            "Type": Name("Annot"), "Subtype": Name("Link"), "Rect": rect, "Border": [0, 0, 0],
            "Dest": [target_ref, Name("Fit")],
        }))

    def add_script(self, key: str, source: str) -> None:
        """Document-open JavaScript; a key already present is not added twice."""
        self.scripts.setdefault(key, source)

    def form_fonts(self) -> dict[str, Ref]:
        """Fonts for form fields (/DR): Courier-Bold, Helvetica-Bold, ZapfDingbats."""
        if self._fonts is None:
            def base14(name: str, encoded: bool = True) -> Ref:
                font = {"Type": Name("Font"), "Subtype": Name("Type1"), "BaseFont": Name(name)}
                if encoded:
                    font["Encoding"] = Name("WinAnsiEncoding")
                return self.writer.add(font)
            self._fonts = {"Cour": base14("Courier-Bold"), "Helv": base14("Helvetica-Bold"),
                           "ZaDb": base14("ZapfDingbats", encoded=False)}
        return self._fonts

    def write(self, fp: BinaryIO, *, title: Optional[str] = None, fullscreen: bool = False,
              layout: Optional[str] = None) -> None:
        if not self.pages:
            raise ValueError("document has no pages")
        w = self.writer
        for ref, page in self.pages:
            w.set(ref, page)
        w.set(self.pages_root, {"Type": Name("Pages"), "Kids": [r for r, _ in self.pages],
                                "Count": len(self.pages)})
        catalog: dict[str, Any] = {"Type": Name("Catalog"), "Pages": self.pages_root}
        if layout:
            catalog["PageLayout"] = Name(layout)
        if fullscreen:
            catalog["PageMode"] = Name("FullScreen")
            catalog["ViewerPreferences"] = {"NonFullScreenPageMode": Name("UseOutlines")
                                            if self.bookmarks else Name("UseNone")}
        elif self.bookmarks:
            catalog["PageMode"] = Name("UseOutlines")
        if self.fields:
            catalog["AcroForm"] = {"Fields": list(self.fields), "DR": {"Font": self.form_fonts()},
                                   "DA": "/Helv 12 Tf 0 g"}
        if self.scripts:
            catalog["OpenAction"] = {"S": Name("JavaScript"), "JS": "\n".join(self.scripts.values())}
        if self.bookmarks:
            catalog["Outlines"] = self._outlines()
        w.set(self.catalog, catalog)
        info = {"Producer": "pixelpdf"}
        if title:
            info["Title"] = title
        w.set(self.info, info)
        w.write(fp, self.catalog, self.info)

    def _outlines(self) -> Ref:
        w = self.writer
        root = w.reserve()
        items = [w.reserve() for _ in self.bookmarks]
        for i, ((title, index), ref) in enumerate(zip(self.bookmarks, items)):
            item = {"Title": title, "Parent": root, "Dest": [self.pages[index][0], Name("Fit")]}
            if i > 0:
                item["Prev"] = items[i - 1]
            if i + 1 < len(items):
                item["Next"] = items[i + 1]
            w.set(ref, item)
        w.set(root, {"Type": Name("Outlines"), "First": items[0], "Last": items[-1],
                     "Count": len(items)})
        return root


def image_page(sink: PageSink, pixels: np.ndarray, dpi: float, *, compression: int = 6,
               extra: Optional[dict] = None) -> Ref:
    """A page showing `pixels` edge to edge, 1 px = 72/dpi pt."""
    height, width = pixels.shape[:2]
    s = 72.0 / dpi
    image = sink.writer.add(encode_image(pixels, level=compression))
    content = b"q %s 0 0 %s 0 0 cm /Im0 Do Q" % (serialize(width * s), serialize(height * s))
    page = {
        "MediaBox": [0, 0, width * s, height * s],
        "Resources": {"XObject": {"Im0": image}},
        "Contents": sink.writer.add(Stream({}, content)),
    }
    page.update(extra or {})
    return sink.add_page(page)
