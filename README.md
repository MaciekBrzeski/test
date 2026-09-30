# pixelpdf

Generate PDF documents where every pixel is set in code. A numpy rendering
engine draws shapes, bitmap text with animated effects, 2D lighting with
shadows, particles and spinners, and the PDF writer stores the result
losslessly on A4 pages. Flipbook animation and in-PDF games come in later
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

## Engine

Everything lives in `pixelpdf.engine` and draws onto a `Canvas`.
Coordinates are pixels, and integer values are pixel *centres*.

```python
from pixelpdf import Document
from pixelpdf.engine import (Light, apply_lighting, bloom, circle, draw_text, glow,
                             linear_gradient, rect, text_fx as fx)

doc = Document()
c = doc.new_page(background="#202030").canvas

rect(c, 100, 100, 400, 200, linear_gradient(100, 0, 500, 0, [(0, "#2e86de"), (1, "#8e44ad")]),
     radius=24)
circle(c, 700, 200, 80, "#e4572e")
draw_text(c, "Hello", 100, 400, scale=6, offsets=fx.wave(t=0.3), colors=fx.rainbow(t=0.3))

apply_lighting(c, [Light(600, 500, "#ffcc88", radius=900)], ambient=0.2, white=2.5)
glow(c, 600, 500, 40, "#ffcc88")
bloom(c)
doc.save("engine.pdf")
```

| Module | What it does |
|---|---|
| `raster` | Lines (anti-aliased, or pixel-exact Bresenham), polylines, circles, rings, arcs, ellipses, rounded rects, polygons. Linear and radial gradient paints. Blend modes: normal, add, multiply, screen. |
| `font`, `text_fx` | Built-in 5×7 bitmap font covering printable ASCII, scaled in whole pixels. Per-character offsets and colours drive the effects: typewriter, wave, bounce, rainbow, fade-in, glitch. |
| `light` | Point and spot lights with smooth falloff. Shadows from any occluder mask, hard or soft, using polar shadow maps. Reinhard tone mapping, glow, bloom, vignette. |
| `particles` | Seeded, vectorised particle systems with emitters and bursts. Gravity, wind, drag, wall and mask collisions with restitution. Colour, fade and size ramps over lifetime. Additive or normal splatting. |
| `spinners` | Arc (Material-style), dots, bars (iOS-style), pulse and orbit spinners, each a seamless loop. |
| `anim` | Easing curves, `Keyframes` tracks, `render_frames(draw, w, h, duration, fps)`, contact sheets, PNG frame export. |

Frames are pure functions of time `t`, so any frame can be rendered on its
own and renders are reproducible. Particle simulations are the exception:
they are stateful and have to be stepped in order.

## Demos

```bash
pip install -e .[dev]
python demos/static_page.py                          # out/static_page.pdf
python demos/engine_showcase.py --frames out/frames  # out/engine_showcase.pdf + PNGs
```

- **`static_page`:** a gradient, a colour wheel, a Phong-lit sphere, a
  Mandelbrot zoom and a strip of 1-px test patterns. The test patterns turn
  grey if anything between the canvas and the screen resamples the image.
- **`engine_showcase`:**
  - Page 1 shows every engine feature: primitives, text effects and
    spinners as filmstrips, a lit scene with soft shadows, and a particle
    fountain bouncing off obstacles.
  - Page 2 shows one animation (moving light, particles, spinner, wave text)
    as a contact sheet of its frames.

## Tests

```bash
python -m pytest
```

- **Round-trip:** images are decoded by qpdf (through `pikepdf`) and must
  match byte for byte.
- **Render check:** pages are rendered with PDFium (through `pypdfium2`) and
  must match pixel for pixel.
- **Validity:** qpdf's syntax check must pass.
- **Engine:** primitives are checked for exact coverage and area, glyphs
  for pixel-exact output, lights for falloff and shadow geometry, and
  particles for physics, collisions and determinism.

## Layout

```
pixelpdf/
  pdf/objects.py   PDF object model and serialisation
  pdf/writer.py    object table, xref and trailer (no dependencies)
  pdf/image.py     lossless image XObjects (Flate + adaptive PNG prediction)
  engine/canvas.py numpy framebuffer, compositing and blend modes
  engine/raster.py SDF-based primitives and gradient paints
  engine/font.py   bitmap font and text drawing
  engine/text_fx.py  animated text effects
  engine/light.py  lights, shadow maps, tone mapping, glow, bloom, vignette
  engine/particles.py  particle systems
  engine/spinners.py loading spinners
  engine/anim.py   easing, keyframes, frame rendering, contact sheets
  engine/filters.py  blur, resize, smoothstep
  engine/png.py    PNG export
  document.py      Document / Page API
demos/             runnable examples
tests/
```

## Roadmap

1. ✅ **Writer and static page:** lossless, pixel-exact A4 pages.
2. ✅ **Engine:** drawing primitives, bitmap font and text effects, 2D
   lighting with shadows and bloom, particle systems, spinners, timeline.
3. **Flipbook backend:** one page per frame with auto-advance (`/Dur`,
   `/Trans`), shared backgrounds and per-frame dirty rectangles to keep
   files small.
4. **Interactive backend:** embedded JavaScript games and simulations,
   rendered to a grid of form fields (Chrome/Edge and Acrobat).
5. **Showcase PDF** and a table of which viewer supports what.
