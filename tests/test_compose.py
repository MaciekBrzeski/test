import io
import json

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.compose import Composer
from pixelpdf.interactive import InteractiveDocument
from pixelpdf.interactive.games import add_game_page

from .conftest import render_page
from .test_interactive import needs_chromium, run_e2e

pikepdf = pytest.importorskip("pikepdf")

SIZE = (120, 90)


def solid(color):
    return Canvas(*SIZE, background=color)


def game_doc(dpi=72, games=1):
    doc = InteractiveDocument(dpi=dpi)
    for _ in range(games):
        page = doc.new_page(background=0, size=SIZE)
        page.display(10, 10, 5, 3, 10, [None, "#ff0000"])
        page.set_game("PX.run({});")
    return doc


def build(rng):
    book = Composer(dpi=72, title="mix")
    cover = book.add_canvas(solid("#102030"))
    anim = book.flipbook(fps=10, size=SIZE, tile=8)
    frames = []
    for i in range(4):
        f = anim.new_frame("#ffffff")
        f.fill_rect(10 + 5 * i, 20, 8, 8, "#e4572e")
        frames.append(f)
        anim.add_frame(f)
    games = book.add_interactive(game_doc(games=2))
    end = book.add_canvas(solid("#abcdef"), duration=2.0, transition="fade")
    book.link(cover, (0, 0, 60, 45), games[0])
    book.bookmark("Cover", cover)
    book.bookmark("Games", games[0])
    return book, cover, frames, games, end


def test_page_order_and_kinds(rng):
    book, cover, frames, games, end = build(rng)
    assert (cover, games, end) == (0, [5, 6], 7)
    with pikepdf.open(io.BytesIO(book.to_bytes())) as pdf:
        assert pdf.check_pdf_syntax() == []
        assert len(pdf.pages) == 8
        assert "/Dur" not in pdf.pages[0].obj
        assert all(float(pdf.pages[i].obj.Dur) == pytest.approx(0.1) for i in range(1, 5))
        assert float(pdf.pages[7].obj.Dur) == 2.0 and pdf.pages[7].obj.Trans.S == pikepdf.Name.Fade
        assert str(pdf.docinfo.Title) == "mix"
        fields = {str(f.T) for f in pdf.Root.AcroForm.Fields}
        assert {"g0_px0_1", "g1_px0_1"} <= fields
        js = str(pdf.Root.OpenAction.JS)
        assert js.count("function PXRuntime(") == 1
        assert '"id": "g0", "page": 5' in js and '"id": "g1", "page": 6' in js


def test_every_static_and_flipbook_page_renders_exactly(rng):
    book, cover, frames, games, end = build(rng)
    data = book.to_bytes()
    np.testing.assert_array_equal(render_page(data, cover, 72), solid("#102030").pixels)
    for i, frame in enumerate(frames):
        np.testing.assert_array_equal(render_page(data, 1 + i, 72), frame.pixels)
    np.testing.assert_array_equal(render_page(data, end, 72), solid("#abcdef").pixels)


def test_links_and_bookmarks(rng):
    book, *_ = build(rng)
    with pikepdf.open(io.BytesIO(book.to_bytes())) as pdf:
        link = [a for a in pdf.pages[0].obj.Annots if a.Subtype == pikepdf.Name.Link][0]
        assert [float(v) for v in link.Rect] == [0, 45, 60, 90]  # top-left quarter
        assert link.Dest[0].objgen == pdf.pages[5].obj.objgen
        assert pdf.Root.PageMode == pikepdf.Name.UseOutlines
        with pdf.open_outline() as outline:
            titles = [item.title for item in outline.root]
        assert titles == ["Cover", "Games"]


def test_fullscreen_option():
    book = Composer(dpi=72, fullscreen=True)
    book.add_canvas(solid(0))
    with pikepdf.open(io.BytesIO(book.to_bytes())) as pdf:
        assert pdf.Root.PageMode == pikepdf.Name.FullScreen


def test_composer_validation():
    book = Composer(dpi=72)
    with pytest.raises(ValueError):
        book.to_bytes()                           # empty
    with pytest.raises(ValueError):
        book.add_interactive(game_doc(dpi=144))   # DPI mismatch
    with pytest.raises(TypeError):
        book.flipbook(dpi=10)
    with pytest.raises(ValueError):
        book.add_canvas(solid(0), duration=0)
    book.add_canvas(solid(0))
    with pytest.raises(IndexError):
        book.link(0, (0, 0, 1, 1), 5)
    anim = book.flipbook(size=SIZE)
    anim.add_frame(anim.new_frame())
    with pytest.raises(ValueError):
        anim.save(io.BytesIO())                   # composed flipbooks save via the composer


# -- end to end, in Chromium's PDF viewer ------------------------------------

@needs_chromium
def test_e2e_link_jumps_to_a_running_game(tmp_path):
    book = Composer(dpi=144)
    cover = Canvas(1191, 1684, background="#203040")
    cover.fill_rect(100, 100, 400, 200, "#e4572e")          # the link area
    book.add_canvas(cover)
    games = InteractiveDocument(dpi=144)
    add_game_page(games, "fireworks")
    (target,) = book.add_interactive(games)
    book.link(0, (100, 100, 400, 200), target)
    pdf = tmp_path / "linked.pdf"
    book.save(pdf)

    spec = {"bg": [32, 48, 64], "width": 1191, "click": [300, 200]}
    result = run_e2e(pdf, "link:" + json.dumps(spec), tmp_path)
    assert result["jumped"] > 10000     # the view changed to another page
    assert result["changed"] > 50       # and the game there is running
