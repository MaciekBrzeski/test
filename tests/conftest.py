import numpy as np
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(1234)


def render_page(pdf_bytes: bytes, page_index: int, dpi: float) -> np.ndarray:
    """Rasterise one page with PDFium (Chrome's PDF engine) at `dpi`, as RGB."""
    pdfium = pytest.importorskip("pypdfium2")
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        bitmap = doc[page_index].render(scale=dpi / 72, rev_byteorder=True)
        return bitmap.to_numpy()[:, :, :3].copy()
    finally:
        doc.close()
