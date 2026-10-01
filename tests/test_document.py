import io

import numpy as np
import pytest

from pixelpdf import Document

from .conftest import render_page

pikepdf = pytest.importorskip("pikepdf")


def random_page(doc, rng, **kwargs):
    page = doc.new_page(**kwargs)
    page.canvas.pixels[:] = rng.integers(0, 256, page.canvas.pixels.shape, dtype=np.uint8)
    return page


@pytest.mark.parametrize("dpi", [72, 144, 288])
def test_render_is_pixel_exact(rng, dpi):
    doc = Document(dpi=dpi)
    page = random_page(doc, rng)
    rendered = render_page(doc.to_bytes(), 0, dpi)
    assert rendered.shape == page.canvas.pixels.shape
    np.testing.assert_array_equal(rendered, page.canvas.pixels)


def test_grayscale_render_is_pixel_exact(rng):
    doc = Document(dpi=72, mode="L")
    page = random_page(doc, rng)
    rendered = render_page(doc.to_bytes(), 0, 72)
    np.testing.assert_array_equal(rendered, np.repeat(page.canvas.pixels, 3, axis=2))


def test_orientation_top_left_origin():
    doc = Document(dpi=72)
    page = doc.new_page(background=0, size=(10, 6))
    page.canvas.set_pixel(0, 0, "#ff0000")      # top-left
    page.canvas.set_pixel(9, 5, "#0000ff")      # bottom-right
    rendered = render_page(doc.to_bytes(), 0, 72)
    assert rendered[0, 0].tolist() == [255, 0, 0]
    assert rendered[5, 9].tolist() == [0, 0, 255]


def test_structure_and_metadata(rng):
    doc = Document(dpi=144, title="Pixel test")
    random_page(doc, rng)
    doc.new_page(background="#336699", size=(100, 50))
    data = doc.to_bytes()
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert pdf.check_pdf_syntax() == []
        assert len(pdf.pages) == 2
        assert [float(v) for v in pdf.pages[0].MediaBox] == [0, 0, 595, 842]
        assert [float(v) for v in pdf.pages[1].MediaBox] == [0, 0, 50, 25]
        assert str(pdf.docinfo.Title) == "Pixel test"
        image = pdf.pages[0].Resources.XObject.Im0
        assert (int(image.Width), int(image.Height)) == (1190, 1684)
        assert bool(image.Interpolate) is False


def test_output_is_deterministic(rng):
    def build():
        doc = Document(dpi=72)
        page = doc.new_page()
        page.canvas.fill_rect(10, 10, 100, 50, "#abcdef")
        return doc.to_bytes()

    assert build() == build()


def test_save_to_path(tmp_path):
    doc = Document(dpi=72)
    doc.new_page()
    target = tmp_path / "out.pdf"
    doc.save(target)
    assert target.read_bytes().startswith(b"%PDF-1.7")
    assert target.read_bytes().rstrip().endswith(b"%%EOF")


def test_empty_document_rejected():
    with pytest.raises(ValueError):
        Document().to_bytes()
