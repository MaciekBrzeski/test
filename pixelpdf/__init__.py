"""pixelpdf — generate PDF documents where every pixel is set programmatically."""

from .compose import Composer
from .document import Document, Page
from .engine.canvas import A4_MM, A4_PT, Canvas, a4_size, parse_color
from .flipbook import Flipbook

__all__ = ["A4_MM", "A4_PT", "Canvas", "Composer", "Document", "Flipbook", "Page", "a4_size",
           "parse_color"]
__version__ = "0.1.0"
