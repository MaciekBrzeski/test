"""Flipbook animation: one PDF page per frame, advancing automatically.

Each page carries /Dur (seconds before the viewer advances) and /Trans
(the transition effect). The document opens in full-screen mode, where
Acrobat/Adobe Reader honour /Dur. Viewers that ignore it show the frames
as ordinary pages.

Pages are stored as a *keyframe* plus *patches*. A keyframe is a
full-page image shared by many pages. Each frame is compared with the
keyframes and only the rectangles that differ are stored, as small images
drawn on top. Identical patches and identical frames are stored once,
so looping content (spinners, cycling text) costs almost nothing after
its first cycle. Every page still renders pixel-for-pixel like the frame
it came from.

    book = Flipbook(fps=12)
    for i in range(48):
        frame = book.new_frame()
        draw(frame, i / 12)
        book.add_frame(frame)
    book.save("anim.pdf")

Frames are encoded as they are added, so memory stays bounded by the
keyframes kept for comparison, however long the animation is.
"""

from __future__ import annotations

import hashlib
import io
import math
import os
from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional, Union

import numpy as np

from .engine.canvas import Canvas, Color, a4_size
from .pdf.image import encode_image
from .pdf.objects import Name, Ref, Stream, serialize
from .pdf.writer import PdfWriter

__all__ = ["Flipbook", "FlipbookStats", "TRANSITIONS", "dirty_rects"]

POINTS_PER_INCH = 72.0
_OBJECT_OVERHEAD = 160  # approx. bytes per image object: dictionary, xref entry, draw op

TRANSITIONS = {
    "replace": "R", "dissolve": "Dissolve", "fade": "Fade", "wipe": "Wipe", "push": "Push",
    "cover": "Cover", "uncover": "Uncover", "split": "Split", "blinds": "Blinds",
    "box": "Box", "glitter": "Glitter", "fly": "Fly",
}


@dataclass
class FlipbookStats:
    frames: int = 0
    keyframes: int = 0
    patches: int = 0
    """Patch placements across all frames (including reused ones)."""
    images: int = 0
    """Distinct image objects stored (keyframes + unique patches)."""
    reused_images: int = 0
    reused_frames: int = 0
    image_bytes: int = 0
    """Compressed size of all stored images."""


def dirty_rects(mask: np.ndarray, tile: int = 32, gap: int = 0) -> list[tuple[int, int, int, int]]:
    """Cover the True pixels of `mask` with disjoint rectangles (x, y, w, h).

    Works on a grid of `tile`-sized cells. Gaps of up to `gap` clean cells
    between dirty ones are filled first (morphological closing), trading a
    few unchanged pixels for fewer, larger rectangles. Runs of dirty cells
    in a row are merged, runs repeating exactly on the next row extend
    downwards, and each rectangle is then shrunk to the exact bounding box
    of its dirty pixels.
    """
    h, w = mask.shape
    th, tw = -(-h // tile), -(-w // tile)
    padded = np.zeros((th * tile, tw * tile), dtype=bool)
    padded[:h, :w] = mask
    cells = padded.reshape(th, tile, tw, tile).any(axis=(1, 3))
    if gap > 0:
        cells = ~_dilate(~_dilate(cells, gap), gap)  # closing; borders don't erode

    spans: list[tuple[int, int, int, int]] = []  # (tx0, tx1, ty0, ty1) in cells
    open_runs: dict[tuple[int, int], int] = {}   # (tx0, tx1) -> starting row
    for ty in range(th + 1):
        runs = _runs(cells[ty]) if ty < th else []
        next_open = {run: open_runs.get(run, ty) for run in runs}
        for run, ty0 in open_runs.items():
            if run not in next_open:
                spans.append((run[0], run[1], ty0, ty))
        open_runs = next_open

    rects = []
    for tx0, tx1, ty0, ty1 in spans:
        x0, x1 = tx0 * tile, min(tx1 * tile, w)
        y0, y1 = ty0 * tile, min(ty1 * tile, h)
        sub = mask[y0:y1, x0:x1]
        rows = np.flatnonzero(sub.any(axis=1))
        cols = np.flatnonzero(sub.any(axis=0))
        if len(rows) == 0:  # only gap-filled cells
            continue
        rects.append((x0 + int(cols[0]), y0 + int(rows[0]),
                      int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)))
    return sorted(rects, key=lambda r: (r[1], r[0]))


def _dilate(a: np.ndarray, r: int) -> np.ndarray:
    """Binary dilation by a (2r+1)^2 square, treating outside as False."""
    h, w = a.shape
    padded = np.zeros((h + 2 * r, w + 2 * r), dtype=bool)
    padded[r:r + h, r:r + w] = a
    out = np.zeros_like(a)
    for dy in range(2 * r + 1):
        for dx in range(2 * r + 1):
            out |= padded[dy:dy + h, dx:dx + w]
    return out


def _bounding_rect(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if len(rows) == 0:
        return []
    return [(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))]


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    """Half-open [start, end) runs of True values."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], row.astype(np.int8), [0]])))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


class Flipbook:
    def __init__(self, dpi: float = 144, fps: float = 12.0, *, mode: str = "RGB",
                 size: Optional[tuple[int, int]] = None, title: Optional[str] = None,
                 transition: str = "replace", transition_duration: float = 0.0,
                 fullscreen: bool = True, tile: int = 32, keyframe_threshold: float = 0.35,
                 max_keyframes: int = 8, compression: int = 6):
        """
        dpi, size: page resolution; size (w, h) in pixels defaults to A4.
        fps: default frame rate; each frame shows for 1/fps s unless given.
        transition: one of TRANSITIONS, applied when a page appears.
        tile: dirty-rectangle grid size in pixels. Smaller tiles store fewer
            unchanged pixels but create more image objects.
        keyframe_threshold: store a frame as a new keyframe when more than
            this fraction of its pixels differs from every existing keyframe.
        max_keyframes: how many recent keyframes new frames are compared with.
        """
        if fps <= 0 or dpi <= 0:
            raise ValueError("fps and dpi must be positive")
        if transition not in TRANSITIONS:
            raise ValueError(f"transition must be one of {sorted(TRANSITIONS)}")
        self.dpi = dpi
        self.fps = fps
        self.mode = mode
        self.width, self.height = size or a4_size(dpi)
        self.title = title
        self.transition = transition
        self.transition_duration = transition_duration
        self.fullscreen = fullscreen
        self.tile = tile
        self.keyframe_threshold = keyframe_threshold
        self.max_keyframes = max_keyframes
        self.compression = compression
        self.stats = FlipbookStats()

        self._writer = PdfWriter()
        self._catalog = self._writer.reserve()
        self._pages_root = self._writer.reserve()
        self._info = self._writer.reserve()
        self._kids: list[Ref] = []
        self._keyframes: list[tuple[np.ndarray, Ref]] = []
        self._images: dict[bytes, Ref] = {}
        self._pages: dict[bytes, tuple[Ref, dict]] = {}
        self._pending: dict[bytes, Stream] = {}  # encoded while costing layouts

    # -- frames --------------------------------------------------------------

    def new_frame(self, background: Color = 255) -> Canvas:
        """A blank canvas of the page size, to draw a frame on."""
        return Canvas(self.width, self.height, self.mode, background)

    def add_frame(self, canvas: Canvas, duration: Optional[float] = None, *,
                  advance: bool = True, transition: Optional[str] = None) -> None:
        """Append a page showing `canvas`.

        duration: seconds on screen (default 1/fps). advance=False leaves
        the page up until the viewer moves on, e.g. for a title page.
        """
        if (canvas.width, canvas.height) != (self.width, self.height):
            raise ValueError(f"frame is {canvas.width}x{canvas.height}, "
                             f"flipbook pages are {self.width}x{self.height}")
        if canvas.mode != self.mode:
            raise ValueError(f"frame mode {canvas.mode} differs from flipbook mode {self.mode}")
        if transition is not None and transition not in TRANSITIONS:
            raise ValueError(f"transition must be one of {sorted(TRANSITIONS)}")
        if duration is None:
            duration = 1.0 / self.fps
        if advance and not (duration > 0 and math.isfinite(duration)):
            raise ValueError("frame duration must be a positive number of seconds")
        pixels = canvas.pixels
        base, dirty = self._closest_keyframe(pixels)

        if base is None or dirty.mean() > self.keyframe_threshold:
            ref = self._image(pixels)
            self._keyframes.append((pixels.copy(), ref))
            self._keyframes = self._keyframes[-self.max_keyframes:]
            self.stats.keyframes += 1
            placements = [(ref, 0, 0, self.width, self.height)]
        else:
            placements = [(base, 0, 0, self.width, self.height)]
            for x, y, w, h in self._cheapest_cover(pixels, dirty):
                placements.append((self._image(pixels[y:y + h, x:x + w]), x, y, w, h))
                self.stats.patches += 1
            self._pending.clear()

        self._add_page(placements, duration if advance else None, transition or self.transition)
        self.stats.frames += 1

    def add_animation(self, draw: Callable[[Canvas, float], None], duration: float, *,
                      fps: Optional[float] = None, background: Color = 255,
                      start: float = 0.0) -> int:
        """Render draw(canvas, t) for each frame time and append the frames in order.

        Returns the number of frames added. Frames are rendered in time
        order, so stateful simulations can be stepped inside `draw`.
        """
        fps = fps or self.fps
        count = max(1, round(duration * fps))
        for i in range(count):
            frame = self.new_frame(background)
            draw(frame, start + i / fps)
            self.add_frame(frame, 1.0 / fps)
        return count

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

    # -- internals -----------------------------------------------------------

    def _closest_keyframe(self, pixels: np.ndarray) -> tuple[Optional[Ref], Optional[np.ndarray]]:
        best_ref, best_mask, best_count = None, None, None
        for key_pixels, ref in reversed(self._keyframes):
            mask = (key_pixels != pixels).any(axis=2)
            count = int(mask.sum())
            if best_count is None or count < best_count:
                best_ref, best_mask, best_count = ref, mask, count
                if count == 0:
                    break
        return best_ref, best_mask

    def _cheapest_cover(self, pixels: np.ndarray, dirty: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Pick the dirty-rectangle layout that is smallest once compressed.

        Fine tiles store the fewest unchanged pixels and let repeating
        content be reused; merged layouts compress better and need fewer
        objects. Rather than guess, each candidate is encoded and costed
        (patches already stored count as free).
        """
        candidates = [dirty_rects(dirty, self.tile)]
        for layout in (dirty_rects(dirty, self.tile, gap=2), _bounding_rect(dirty)):
            if layout not in candidates:
                candidates.append(layout)
        if len(candidates) == 1:
            return candidates[0]
        best, best_cost = None, None
        for rects in candidates:
            cost = 0
            for x, y, w, h in rects:
                key, _ = self._lookup(pixels[y:y + h, x:x + w])
                if key not in self._images:
                    cost += len(self._encoded(key, pixels[y:y + h, x:x + w]).data) + _OBJECT_OVERHEAD
            if best_cost is None or cost < best_cost:
                best, best_cost = rects, cost
        return best

    def _lookup(self, pixels: np.ndarray) -> tuple[bytes, np.ndarray]:
        pixels = np.ascontiguousarray(pixels)
        key = hashlib.blake2b(repr(pixels.shape).encode() + pixels.tobytes(), digest_size=20).digest()
        return key, pixels

    def _encoded(self, key: bytes, pixels: np.ndarray) -> Stream:
        stream = self._pending.get(key)
        if stream is None:
            stream = encode_image(np.ascontiguousarray(pixels), level=self.compression)
            self._pending[key] = stream
        return stream

    def _image(self, pixels: np.ndarray) -> Ref:
        key, pixels = self._lookup(pixels)
        ref = self._images.get(key)
        if ref is not None:
            self.stats.reused_images += 1
            return ref
        stream = self._pending.pop(key, None) or encode_image(pixels, level=self.compression)
        ref = self._writer.add(stream)
        self._images[key] = ref
        self.stats.images += 1
        self.stats.image_bytes += len(stream.data)
        return ref

    def _add_page(self, placements, duration: Optional[float], transition: str) -> None:
        # Identical frames share one content stream and resource dictionary.
        key = hashlib.blake2b(repr([(r.num, x, y, w, h) for r, x, y, w, h in placements]).encode(),
                              digest_size=20).digest()
        shared = self._pages.get(key)
        if shared is None:
            s = POINTS_PER_INCH / self.dpi
            ops = []
            for ref, x, y, w, h in placements:
                ops.append(b"q %s 0 0 %s %s %s cm /Im%d Do Q" % (
                    serialize(w * s), serialize(h * s), serialize(x * s),
                    serialize((self.height - y - h) * s), ref.num))
            content = self._writer.add(Stream({}, b"\n".join(ops)))
            resources = {"XObject": {f"Im{ref.num}": ref for ref, *_ in placements}}
            shared = (content, resources)
            self._pages[key] = shared
        else:
            self.stats.reused_frames += 1

        content, resources = shared
        s = POINTS_PER_INCH / self.dpi
        page = {
            "Type": Name("Page"),
            "Parent": self._pages_root,
            "MediaBox": [0, 0, self.width * s, self.height * s],
            "Resources": resources,
            "Contents": content,
            "Trans": {"Type": Name("Trans"), "S": Name(TRANSITIONS[transition]),
                      "D": self.transition_duration},
        }
        if duration is not None:
            page["Dur"] = duration
        self._kids.append(self._writer.add(page))

    def _write(self, fp: BinaryIO) -> None:
        if not self._kids:
            raise ValueError("flipbook has no frames")
        w = self._writer
        w.set(self._pages_root, {"Type": Name("Pages"), "Kids": list(self._kids),
                                 "Count": len(self._kids)})
        catalog = {"Type": Name("Catalog"), "Pages": self._pages_root,
                   "PageLayout": Name("SinglePage")}
        if self.fullscreen:
            catalog["PageMode"] = Name("FullScreen")
            catalog["ViewerPreferences"] = {"NonFullScreenPageMode": Name("UseNone")}
        w.set(self._catalog, catalog)
        info = {"Producer": "pixelpdf"}
        if self.title:
            info["Title"] = self.title
        w.set(self._info, info)
        w.write(fp, self._catalog, self._info)
