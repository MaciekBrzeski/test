"""pixelpdf — generate PDF documents where every pixel is set programmatically."""

from .document import Document, Page
from .engine.canvas import A4_MM, Canvas, a4_size, parse_color

__all__ = ["A4_MM", "Canvas", "Document", "Page", "a4_size", "parse_color"]
__version__ = "0.1.0"
