import io
import math

import numpy as np
import pytest

from pixelpdf import Document
from pixelpdf.engine import raster as R
from pixelpdf.engine import spinners
from pixelpdf.flipbook import TRANSITIONS, Flipbook, dirty_rects

from .conftest import render_page

pikepdf = pytest.importorskip("pikepdf")


# -- dirty rectangles --------------------------------------------------------

def check_cover(mask, rects):
    covered = np.zeros_like(mask, dtype=int)
    for x, y, w, h in rects:
        assert w > 0 and h > 0
        sub = mask[y:y + h, x:x + w]
        # Tight: every edge row/column of the rect contains a dirty pixel.
        assert sub[0].any() and sub[-1].any() and sub[:, 0].any() and sub[:, -1].any()
        covered[y:y + h, x:x + w] += 1
    assert covered.max() <= 1, "rectangles overlap"
    assert (covered[mask] == 1).all(), "dirty pixel not covered"


@pytest.mark.parametrize("tile", [1, 4, 16, 32])
@pytest.mark.parametrize("gap", [0, 1, 2])
def test_dirty_rects_cover_random_masks(rng, tile, gap):
    for density in (0.001, 0.02, 0.3):
        mask = rng.random((97, 131)) < density
        check_cover(mask, dirty_rects(mask, tile, gap))


def test_gap_closing_merges_nearby_changes():
    mask = np.zeros((64, 256), bool)
    mask[10, 10] = mask[10, 80] = mask[50, 150] = True
    assert len(dirty_rects(mask, 16)) == 3
    assert len(dirty_rects(mask, 16, gap=2)) < 3


def test_dirty_rects_shapes():
    assert dirty_rects(np.zeros((10, 10), bool)) == []
    mask = np.zeros((100, 100), bool)
    mask[10:20, 30:45] = True
    assert dirty_rects(mask, 8) == [(30, 10, 15, 10)]
    mask[70, 5] = True
    assert dirty_rects(mask, 8) == [(30, 10, 15, 10), (5, 70, 1, 1)]


def test_dirty_rects_merge_vertical_runs():
    mask = np.zeros((128, 128), bool)
    mask[:, 32:64] = True  # a full-height column: one rect, not four
    assert dirty_rects(mask, 32) == [(32, 0, 32, 128)]


# -- flipbook ----------------------------------------------------------------

def spinner_frames(book, count, fps):
    frames = []
    for i in range(count):
        f = book.new_frame("#f4f1ea")
        R.rect(f, 10, 10, 120, 30, "#223344")
        spinners.arc_spinner(f, 60, 90, 25, i / fps, "#2e86de")
        spinners.dots_spinner(f, 150, 90, 25, i / fps, "#e4572e", background="#f4f1ea")
        frames.append(f)
        book.add_frame(f)
    return frames


@pytest.mark.parametrize("dpi", [72, 144])
def test_every_page_renders_exactly_like_its_frame(dpi):
    book = Flipbook(dpi=dpi, fps=10, size=(200, 150), tile=16)
    frames = spinner_frames(book, 12, 10)
    data = book.to_bytes()
    assert book.stats.patches > 0 and book.stats.keyframes == 1
    for i, frame in enumerate(frames):
        np.testing.assert_array_equal(render_page(data, i, dpi), frame.pixels)


def test_a4_pages_render_exactly(rng):
    book = Flipbook(dpi=72, fps=5)
    frames = []
    for i in range(3):
        f = book.new_frame()
        f.pixels[100:140, 200 + 30 * i:260 + 30 * i] = rng.integers(0, 256, (40, 60, 3), dtype=np.uint8)
        frames.append(f)
        book.add_frame(f)
    data = book.to_bytes()
    for i, frame in enumerate(frames):
        np.testing.assert_array_equal(render_page(data, i, 72), frame.pixels)


def test_page_timing_transition_and_fullscreen():
    book = Flipbook(dpi=72, fps=8, size=(40, 30), transition="dissolve", transition_duration=0.2)
    book.add_frame(book.new_frame(), advance=False)
    book.add_frame(book.new_frame(0))
    book.add_frame(book.new_frame(128), 1.5, transition="wipe")
    with pikepdf.open(io.BytesIO(book.to_bytes())) as pdf:
        assert pdf.check_pdf_syntax() == []
        assert pdf.Root.PageMode == pikepdf.Name.FullScreen
        p0, p1, p2 = pdf.pages
        assert "/Dur" not in p0.obj
        assert float(p1.obj.Dur) == pytest.approx(1 / 8)
        assert float(p2.obj.Dur) == pytest.approx(1.5)
        assert p1.obj.Trans.S == pikepdf.Name.Dissolve
        assert float(p1.obj.Trans.D) == pytest.approx(0.2)
        assert p2.obj.Trans.S == pikepdf.Name.Wipe
        assert [float(v) for v in p0.MediaBox] == [0, 0, 40, 30]


def test_all_transitions_are_valid_names():
    for name in TRANSITIONS:
        book = Flipbook(dpi=72, size=(10, 10), transition=name)
        book.add_frame(book.new_frame())
        with pikepdf.open(io.BytesIO(book.to_bytes())) as pdf:
            assert pdf.pages[0].obj.Trans.S == pikepdf.Name("/" + TRANSITIONS[name])


def test_looping_content_is_stored_once():
    book = Flipbook(dpi=72, fps=10, size=(200, 150), tile=16)
    spinner_frames(book, 10, 10)             # one spinner period (1.0 s)
    first_cycle = book.stats.images
    spinner_frames(book, 10, 10)             # the same period again
    assert book.stats.images == first_cycle  # nothing new stored
    assert book.stats.reused_frames == 10


def test_identical_frames_share_content():
    book = Flipbook(dpi=72, size=(50, 50))
    for _ in range(5):
        book.add_frame(book.new_frame("#123456"))
    assert (book.stats.images, book.stats.reused_frames) == (1, 4)


def test_new_keyframe_when_most_pixels_change():
    book = Flipbook(dpi=72, size=(60, 40), keyframe_threshold=0.5)
    book.add_frame(book.new_frame(0))
    f = book.new_frame(0)
    f.fill_rect(0, 0, 10, 10, 255)
    book.add_frame(f)                         # small change: a patch
    book.add_frame(book.new_frame(255))       # everything changed: a new keyframe
    book.add_frame(book.new_frame(0))         # back to the first keyframe, no new image
    assert book.stats.keyframes == 2
    assert book.stats.patches == 1
    assert book.stats.images == 3


def test_flipbook_is_much_smaller_than_independent_pages():
    fps, count = 10, 20
    book = Flipbook(dpi=72, fps=fps)
    doc = Document(dpi=72)
    for i in range(count):
        f = book.new_frame()
        R.rect(f, 0, 0, f.width, 120, "#1d1d2b")
        R.circle(f, 300, 400, 150, R.radial_gradient(250, 350, 220, [(0, "#ffe29a"), (1, "#e4572e")]))
        spinners.arc_spinner(f, 100 + 20 * i, 700, 30, i / fps, "#2e86de")
        book.add_frame(f)
        doc.add_canvas(f)
    assert len(book.to_bytes()) * 5 < len(doc.to_bytes())


def test_add_animation_passes_times_in_order():
    seen = []
    book = Flipbook(dpi=72, fps=4, size=(20, 20))
    n = book.add_animation(lambda c, t: seen.append(t), duration=1.0)
    assert n == 4 and seen == [0, 0.25, 0.5, 0.75]
    assert book.stats.frames == 4


def test_repeated_save_is_stable():
    book = Flipbook(dpi=72, size=(20, 20))
    book.add_frame(book.new_frame())
    assert book.to_bytes() == book.to_bytes()


@pytest.mark.parametrize("kwargs", [dict(fps=0), dict(transition="spin")])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        Flipbook(**kwargs)


def test_invalid_frames():
    book = Flipbook(dpi=72, size=(20, 20))
    with pytest.raises(ValueError):
        book.to_bytes()
    from pixelpdf import Canvas
    with pytest.raises(ValueError):
        book.add_frame(Canvas(10, 10))
    with pytest.raises(ValueError):
        book.add_frame(Canvas(20, 20, mode="L"))
    with pytest.raises(ValueError):
        book.add_frame(book.new_frame(), duration=-1)
    with pytest.raises(ValueError):
        book.add_frame(book.new_frame(), duration=math.inf)
