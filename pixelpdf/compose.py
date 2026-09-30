"""Compose one PDF from static pages, flipbook animations and interactive games.

    book = Composer(title="Showcase")
    cover = book.add_canvas(cover_canvas)               # static, pixel-exact
    anim = book.flipbook(fps=12)                        # frames appended in order
    for t in ...:
        anim.add_frame(draw(t))
    games = book.add_interactive(interactive_document)  # pages with live games
    book.link(cover, (x, y, w, h), games[0])            # clickable contents
    book.bookmark("Games", games[0])
    book.save("showcase.pdf")

Pages appear in the order they are added. Every backend writes into the
same file: images and patches are shared per flipbook, the form fields and
scripts of all interactive pages are merged, and each game only runs
while its own page is in view.
"""

from __future__ import annotations

import io
import os
from typing import BinaryIO, Optional, Union

from .engine.canvas import Canvas
from .flipbook import TRANSITIONS, Flipbook
from .interactive.builder import InteractiveDocument
from .pdf.objects import Name
from .pdf.pages import PageSink, image_page

__all__ = ["Composer"]


class Composer:
    def __init__(self, dpi: float = 144, *, title: Optional[str] = None,
                 fullscreen: bool = False, compression: int = 6):
        """
        fullscreen: ask the viewer to open in full screen, which is where
            Acrobat auto-advances flipbook pages. Off by default because it
            also takes over the reading of static and game pages.
        """
        self.dpi = dpi
        self.title = title
        self.fullscreen = fullscreen
        self.compression = compression
        self._sink = PageSink()

    def __len__(self) -> int:
        return len(self._sink)

    def add_canvas(self, canvas: Canvas, *, duration: Optional[float] = None,
                   transition: Optional[str] = None) -> int:
        """Append a static page showing `canvas`; returns its page index.

        duration/transition make it a timed page, like a flipbook frame.
        """
        extra = {}
        if duration is not None:
            if not duration > 0:
                raise ValueError("duration must be positive")
            extra["Dur"] = duration
        if transition is not None:
            if transition not in TRANSITIONS:
                raise ValueError(f"transition must be one of {sorted(TRANSITIONS)}")
            extra["Trans"] = {"Type": Name("Trans"), "S": Name(TRANSITIONS[transition])}
        index = len(self._sink)
        image_page(self._sink, canvas.pixels, self.dpi, compression=self.compression, extra=extra)
        return index

    def flipbook(self, fps: float = 12.0, **options) -> Flipbook:
        """A Flipbook whose frames are appended to this document as they are added.

        Accepts Flipbook's options (transition, tile, keyframe_threshold, ...);
        page size defaults to A4 at the composer's DPI.
        """
        for name in ("dpi", "sink", "title", "fullscreen"):
            if name in options:
                raise TypeError(f"{name} is set by the Composer")
        return Flipbook(self.dpi, fps, sink=self._sink, compression=self.compression, **options)

    def add_interactive(self, doc: InteractiveDocument) -> list[int]:
        """Append all pages of an interactive document; returns their indices."""
        if doc.dpi != self.dpi:
            raise ValueError(f"interactive document is {doc.dpi} DPI, composer is {self.dpi}")
        return doc.emit(self._sink)

    def link(self, page: int, rect: tuple[float, float, float, float], target: int) -> None:
        """Make canvas-pixel area (x, y, w, h) of page `page` jump to page `target`."""
        if not (0 <= page < len(self) and 0 <= target < len(self)):
            raise IndexError("link page or target out of range")
        s = 72.0 / self.dpi
        ref, page_dict = self._sink.page(page)
        height_pt = page_dict["MediaBox"][3]
        x, y, w, h = rect
        self._sink.add_link(page, [x * s, height_pt - (y + h) * s, (x + w) * s, height_pt - y * s],
                            target)

    def bookmark(self, title: str, page: int) -> None:
        """Add an entry to the viewer's outline (sidebar) pointing at `page`."""
        if not 0 <= page < len(self):
            raise IndexError("bookmark page out of range")
        self._sink.bookmarks.append((title, page))

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
        self._sink.write(fp, title=self.title, fullscreen=self.fullscreen)
