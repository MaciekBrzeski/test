# pixelpdf

Generate PDF documents where every pixel is set in code: static A4 pages
now, with animations, lighting, particles and simple games coming in later
milestones.

## How it works

A PDF page has no pixels of its own, so each page embeds one full-page image
built from a numpy framebuffer:

- **Lossless.** Pixels are compressed with Flate after PNG row prediction.
  The decoded samples match the canvas exactly.
- **Crisp.** `/Interpolate false` asks viewers not to blur pixels when they
  zoom.
- **Exact mapping.** The page size comes from the pixel size: 1 px = 72/dpi
  pt. The default of **144 DPI** gives an A4 page of **1191×1684 px**
  (595.5×842 pt, 210.1×297.0 mm).

Use a DPI of the form 72·2ᵏ (72, 144, 288, …). With these, page sizes are
exact in the 32-bit floats viewers use, and a render at zoom `dpi/72` is
pixel-for-pixel identical to the canvas. The tests check this with PDFium,
the engine inside Chrome's PDF viewer. Other DPIs such as 150 or 300 still
store exact pixels, but viewers may map the page one device pixel off and
resample it.

## Usage

```python
from pixelpdf import Document

doc = Document(dpi=144, title="Hello pixels")
page = doc.new_page(background="#ffffff")   # A4 canvas
c = page.canvas

c.set_pixel(10, 10, "#ff0000")              # (0, 0) is the top-left corner
c.fill_rect(20, 20, 100, 50, (0, 128, 255))
c.pixels[200:300, 200:300] = 0              # raw (H, W, C) uint8 numpy array

doc.save("hello.pdf")
```

Canvas modes are `RGB` (default), `L` (grayscale) and `CMYK`. Colours can be
given as an int (gray level), a tuple, or `#rgb` / `#rrggbb`.

## Demo

```bash
pip install -e .[dev]
python demos/static_page.py          # writes out/static_page.pdf
```

The demo page contains a gradient, a colour wheel, a Phong-lit sphere, a
Mandelbrot zoom and a strip of 1-px test patterns. The test patterns turn
grey if anything between the canvas and the screen resamples the image.

## Tests

```bash
python -m pytest
```

- **Round-trip:** images are decoded by qpdf (through `pikepdf`) and must
  match byte for byte.
- **Render check:** pages are rendered with PDFium (through `pypdfium2`) and
  must match pixel for pixel.
- **Validity:** qpdf's syntax check must pass.

## Layout

```
pixelpdf/
  pdf/objects.py   PDF object model and serialisation
  pdf/writer.py    object table, xref and trailer (no dependencies)
  pdf/image.py     lossless image XObjects (Flate + adaptive PNG prediction)
  engine/canvas.py numpy framebuffer
  document.py      Document / Page API
demos/             runnable examples
tests/
```

## Roadmap

1. ✅ **Writer and static page:** lossless, pixel-exact A4 pages.
2. **Engine:** drawing primitives, bitmap font and text effects, 2D
   lighting with shadows and bloom, particle systems.
3. **Flipbook backend:** one page per frame with auto-advance (`/Dur`,
   `/Trans`), shared backgrounds and per-frame dirty rectangles to keep
   files small.
4. **Interactive backend:** embedded JavaScript games and simulations,
   rendered to a grid of form fields (Chrome/Edge and Acrobat).
5. **Showcase PDF** and a table of which viewer supports what.
