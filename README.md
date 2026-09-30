# pixelpdf

Generate PDF documents where every pixel is set in code. A numpy rendering
engine draws shapes, bitmap text with animated effects, 2D lighting with
shadows, particles and spinners, and the PDF writer stores the result
losslessly on A4 pages. Animations can be exported as flipbook PDFs that
play frame by frame, and interactive PDFs run games and simulations live
in the viewer's JavaScript engine.

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

## Flipbook animation

`Flipbook` turns frames into pages that advance automatically:

```python
from pixelpdf.flipbook import Flipbook
from pixelpdf.engine import spinners

book = Flipbook(fps=12, title="Spinner")             # A4 pages, 144 DPI

def draw(canvas, t):
    spinners.arc_spinner(canvas, 595, 842, 80, t, "#2e86de")

book.add_animation(draw, duration=2.0)              # 24 frames
book.save("spinner.pdf")
```

Frames can also be added one at a time with `book.add_frame(canvas,
duration=None, advance=True, transition=None)`. `advance=False` makes a
page that waits, such as a title page. Transitions are `replace`
(default), `dissolve`, `fade`, `wipe`, `push`, `cover`, `uncover`,
`split`, `blinds`, `box`, `glitter` and `fly`.

**How it plays**
- Each page carries `/Dur` (seconds on screen) and `/Trans` (transition),
  and the document asks to open in full screen.
- Adobe Acrobat and Reader honour this in full-screen mode, so the frames
  play by themselves. To loop, turn on *Preferences > Full Screen > Loop
  after last page*. This hasn't been tested in Acrobat here.
- Other viewers (browsers, most mobile apps) ignore the timing and show
  the frames as pages you scroll through.

**How it stays small**
- A page is a full-page *keyframe* image plus *patches*: tight rectangles
  around the pixels that differ from the keyframe. A frame that differs
  from every keyframe by more than 35% becomes a new keyframe.
- For each frame, a few patch layouts are compressed and the smallest is
  kept. Layouts range from fine tiles to merged tiles to one bounding box.
- Identical patches and identical frames are stored once, so looping
  content costs nothing after its first cycle.
- Frames are encoded as they're added, so memory doesn't grow with the
  animation's length.

**Where it helps.** Flat static areas compress to almost nothing even when
stored whole, so the saving comes from:
- detailed static art that animation plays over (it's stored only once),
- looping content,
- small moving elements.

A region that changes completely every frame, such as a moving light over
a whole scene, costs the same either way. Rendering such a region as 2×2
pixel blocks (`canvas.upscale(2)`) makes it compress about 2.5× better.

**Pixel exactness.** Every page renders exactly like its frame; the tests
check this with PDFium at 72 and 144 DPI. Patches are always stored at
full resolution. Storing them at lower resolution and letting the viewer
enlarge them would be smaller, but PDFium smooths images enlarged 2× by
default, so the result wouldn't be pixel-exact.

## Interactive PDFs (games)

`pixelpdf.interactive` builds pages where a JavaScript program runs inside
the PDF viewer and draws on a live pixel display:

```python
from pixelpdf.interactive.games import build_game

build_game("snake").save("snake.pdf")      # also "breakout", "fireworks"
```

**How the display works.** PDF viewers can't draw pixels from a script,
but they can change the text in form fields. So:
- Each row of the display is a read-only *comb* text field per palette
  colour. A comb field splits its width into equal cells, one per
  character.
- A pixel of colour *k* is a ZapfDingbats ■ in row field *k*.
- Colour 0 is transparent, so the page's static artwork (a pixel-exact
  canvas, as elsewhere in pixelpdf) shows through. It holds the bezel, the
  dim "off" LEDs and the instructions.
- The runtime only rewrites fields whose text changed.

**Input**
- *Keyboard:* click the key box and type. The keystroke script passes each
  key to the game.
- *Buttons:* on-screen push buttons behave like held keys, for mouse and
  touch.
- Arrow keys don't reach PDF scripts, so games use W A S D and space. P
  pauses.

**Measured in Chromium's viewer (PDFium)**
- Timers fire at about 50 Hz.
- A 48×36 display in 6 colours (216 fields), fully redrawn every frame,
  runs at about 22 fps. Games redraw far less, because only changed rows
  are written.
- Changing a field's `fillColor` or `textColor` doesn't repaint in PDFium,
  which is why colours are separate stacked fields.
- Editable fields get a blue highlight, so display fields are read-only.

**Build your own**

```python
from pixelpdf.interactive import InteractiveDocument

doc = InteractiveDocument(fps=30)
page = doc.new_page(background="#101018")            # page.canvas: static art
page.display(x=95, y=300, cols=40, rows=30, cell=25,
             palette=[None, "#ff4d4d", "#2ecc71", "#ffe66d"])
page.hud("score", x=95, y=240, w=500, h=44)
page.key_capture(x=95, y=1100, w=330, h=70)
page.button(" ", x=470, y=1100, w=200, h=70, label="FIRE")
doc.set_game("""
PX.run({
  update: function (px, dt) {
    px.clear(0);
    var x = Math.floor(px.time * 10) % px.W;
    px.rect(x, 10, 3, 3, px.held(' ') ? 2 : 1);
    px.text('HI', 2, 2, 3);
    px.hud('score', 'T ' + px.time.toFixed(1));
  }
});
""")
doc.save("mine.pdf")
```

The runtime API (`px`):
- **Drawing:** `set`, `get`, `rect`, `line`, `clear`, `text` (a 3×5 font),
  `textCentered`.
- **Input:** `keys` (pressed this frame), `pressed(k)`, `held(k)`.
- **Time and randomness:** `random` and `randint` (seeded, deterministic),
  `time`, `frame`, `paused`.
- **Text fields:** `hud(name, text)`.

Scripts are ES5, because Acrobat's JavaScript engine is older than
Chrome's.

**Viewer support**
- **Chrome and Edge:** tested here with headless Chromium.
- **Adobe Acrobat and Reader:** the fields, fonts and JavaScript calls used
  are standard Acrobat features, but untested here.
- **Firefox:** pdf.js runs only part of the Acrobat API; untested.
- **macOS Preview, most mobile apps, printers:** show the static page with
  an empty display.

## Demos

```bash
pip install -e .[dev]
python demos/static_page.py                          # out/static_page.pdf
python demos/engine_showcase.py --frames out/frames  # out/engine_showcase.pdf + PNGs
python demos/flipbook_demo.py                        # out/flipbook.pdf
python demos/games.py                                # out/snake.pdf, breakout.pdf, fireworks.pdf
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
- **`flipbook_demo`:** a title page, then 48 frames at 12 fps.
  - A detailed textured scene is stored once, and sparks bounce over it.
  - A panel with a moving light changes completely every frame.
  - Spinners, wave text and a bouncing ball loop.
  - Also a typewriter caption and a progress bar.
  - The file is about 8 MB; storing whole frames would take about 22 MB.
- **`games`:** Snake, Breakout (with levels and lives) and Fireworks (a
  particle toy with gravity, wind, drag and bouncing sparks). Each is a
  one-page A4 PDF of 130–190 KB.

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
- **Flipbook:** every page must render exactly like its frame. Dirty
  rectangles must be disjoint, tight and cover every changed pixel. Looping
  content must not store new images, and the page timing, transition and
  full-screen entries must be present.
- **Interactive:**
  - PDF structure: field flags, geometry, fonts, actions.
  - The generated script must be valid JavaScript and stay within ES5.
  - Runtime and game logic run in Node against fake fields
    (`tests/js/harness.js`): drawing, which fields get rewritten, input,
    pause, snake eating and crashing, breakout with an autopilot paddle,
    fireworks particle bounds.
  - Chromium's PDF viewer runs the real files (`tests/js/e2e.js`): the
    display must animate, respond to typed keys and freeze on pause.

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
  flipbook.py      Flipbook: keyframes + dirty-rect patches, /Dur + /Trans pages
  interactive/builder.py  form-field display, HUD, buttons, key capture, script
  interactive/runtime.js  in-viewer runtime (ES5): framebuffer, input, main loop
  interactive/games.py    built-in games laid out as A4 pages
  interactive/games/*.js  snake, breakout, fireworks
demos/             runnable examples
tests/
```

## Roadmap

1. ✅ **Writer and static page:** lossless, pixel-exact A4 pages.
2. ✅ **Engine:** drawing primitives, bitmap font and text effects, 2D
   lighting with shadows and bloom, particle systems, spinners, timeline.
3. ✅ **Flipbook backend:** one page per frame with auto-advance (`/Dur`,
   `/Trans`), shared keyframes, dirty-rectangle patches and deduplication.
4. ✅ **Interactive backend:** embedded JavaScript games and simulations,
   rendered to a grid of form fields (Chrome/Edge; Acrobat untested).
5. **Showcase PDF** and a table of which viewer supports what.
