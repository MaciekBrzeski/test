"""Milestone 2 demo: the rendering engine on two A4 pages.

    python demos/engine_showcase.py [output.pdf] [--frames DIR]

Page 1: primitives, text effects, spinners (as filmstrips over time), a
lit scene with soft shadows and bloom, and a particle fountain.
Page 2: one animated scene (moving light, particles, spinner, text)
shown as a contact sheet of its frames.

--frames DIR also writes that animation as numbered PNGs.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pixelpdf import Canvas, Document  # noqa: E402
from pixelpdf.engine import raster as R  # noqa: E402
from pixelpdf.engine import spinners, text_fx as fx  # noqa: E402
from pixelpdf.engine.anim import Keyframes, contact_sheet, frame_times, save_frames  # noqa: E402
from pixelpdf.engine.font import draw_text, measure_text  # noqa: E402
from pixelpdf.engine.light import Light, apply_lighting, bloom, glow, vignette  # noqa: E402
from pixelpdf.engine.particles import Emitter, ParticleSystem  # noqa: E402

PAPER = "#f4f1ea"
INK = "#1d1d2b"
ACCENT = "#e4572e"
BLUE = "#2e86de"
COLUMNS = 3  # contact-sheet columns on page 2


def heading(c: Canvas, text: str, x: int, y: int) -> int:
    draw_text(c, text, x, y, INK, scale=3)
    R.rect(c, x, y + 32, measure_text(text, 3)[0], 3, ACCENT)
    return y + 48


# -- page 1 panels -----------------------------------------------------------

def primitives_panel(w: int, h: int) -> Canvas:
    c = Canvas(w, h, background="#ffffff")
    R.rect(c, 0, 0, w, h, "#d8d4ca", fill=False)
    cy = h // 2
    R.rect(c, 20, cy - 50, 120, 100, R.linear_gradient(20, 0, 140, 0, [(0, BLUE), (1, "#8e44ad")]),
           radius=18)
    R.circle(c, 210, cy, 50, R.radial_gradient(195, cy - 15, 70, [(0, "#ffe29a"), (1, ACCENT)]))
    R.polygon(c, [(290 + 55 + 50 * math.cos(a), cy + 50 * math.sin(a))
                  for a in np.linspace(-math.pi / 2, 3.5 * math.pi, 5, endpoint=False)], "#27ae60")
    for i in range(12):
        a = i * math.pi / 6
        R.line(c, 470, cy, 470 + 48 * math.cos(a), cy + 48 * math.sin(a), INK, width=1 + i / 4)
    R.arc(c, 580, cy, 40, -math.pi / 2, math.pi * 0.9, ACCENT, width=10)
    R.circle(c, 580, cy, 40, "#eeeeee", fill=False, width=2)
    # Anti-aliased vs pixel-exact edges, magnified 6x.
    zoom = Canvas(16, 16, background="#ffffff")
    R.circle(zoom, 7.5, 7.5, 6, INK)
    hard = Canvas(16, 16, background="#ffffff")
    R.circle(hard, 7.5, 7.5, 6, INK, aa=False)
    for i, small in enumerate((zoom, hard)):
        big = small.pixels.repeat(6, 0).repeat(6, 1)
        x = w - 220 + i * 105
        c.blit(big, x, cy - 60)
        draw_text(c, ("aa=True", "aa=False")[i], x + 48, cy + 45, INK, align="center", scale=2)
    return c


def text_filmstrip(w: int, frames: int) -> Canvas:
    fw = (w - (frames + 1) * 8) // frames
    shots = []
    for t in np.linspace(0, 1.2, frames):
        f = Canvas(fw, 150, background="#ffffff")
        draw_text(f, "Wave!", 10, 14, scale=4, offsets=fx.wave(t, amplitude=5), colors=fx.rainbow(t))
        draw_text(f, fx.typewriter("Typing...", t, cps=8), 10, 62, INK, scale=2)
        draw_text(f, "GLITCH", 10, 100, INK, scale=4)
        fx.glitch(f, 10, 100, fw - 20, 36, t, intensity=1.5, seed=2)
        draw_text(f, f"t={t:.2f}s", fw - 6, 138, "#999999", align="right")
        shots.append(f)
    return contact_sheet(shots, frames, gap=8, background=PAPER)


def spinner_filmstrip(w: int, frames: int) -> Canvas:
    kinds = [spinners.arc_spinner, spinners.dots_spinner, spinners.bars_spinner,
             spinners.pulse_spinner, spinners.orbit_spinner]
    colors = [BLUE, ACCENT, INK, "#27ae60", "#8e44ad"]
    size = 96
    rows = []
    for t in np.linspace(0, 1, frames, endpoint=False):
        f = Canvas(size * len(kinds), size, background="#ffffff")
        for i, (fn, col) in enumerate(zip(kinds, colors)):
            kwargs = {"track": "#e5e9f2"} if fn is spinners.arc_spinner else {}
            fn(f, size * i + size / 2 - 0.5, size / 2 - 0.5, size * 0.38, t, col, **kwargs)
        rows.append(f)
    return contact_sheet(rows, 2, gap=8, background=PAPER)


def lit_scene(w: int, h: int, t: float = 0.0, seed: int = 5, texture: bool = True) -> Canvas:
    """Stone floor with pillars, lit by a warm lamp, a cold lamp and a spotlight.

    texture=False skips the noisy stone texture, which compresses much better.
    """
    c = Canvas(w, h, background="#b9b2a4")
    if texture:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, 7, (h // 4 + 1, w // 4 + 1)).repeat(4, 0).repeat(4, 1)[:h, :w]
        c.pixels[:] = np.clip(c.pixels + noise[:, :, None], 0, 255).astype(np.uint8)
    for y in range(0, h, 40):  # tile grout
        R.rect(c, 0, y, w, 2, "#9b9384")
    for x in range(0, w, 40):
        R.rect(c, x, 0, 2, h, "#9b9384")

    solid = Canvas(w, h, mode="L", background=0)
    pillars = [(0.25, 0.35, 22), (0.55, 0.3, 30), (0.7, 0.7, 26), (0.35, 0.72, 18)]
    for fx_, fy, r in pillars:
        R.circle(solid, fx_ * w, fy * h, r, 255, aa=False)
    R.rect(solid, int(0.85 * w), int(0.15 * h), 18, int(0.4 * h), 255, aa=False)
    mask = solid.pixels[:, :, 0] > 0

    orbit = Keyframes([(0, 0.0), (4, 2 * math.pi)], loop=4)(t)
    warm = Light(w * (0.45 + 0.25 * math.cos(orbit)), h * (0.5 + 0.25 * math.sin(orbit)),
                 "#ffc27a", radius=w * 0.75, intensity=1.6, shadow_softness=0.06)
    cold = Light(w * 0.12, h * 0.85, "#5d8cff", radius=w * 0.55, intensity=0.9, shadow_softness=0.03)
    spot = Light(w * 0.95, h * 0.05, "#ff5a7a", radius=w * 0.9, intensity=1.2,
                 direction=math.atan2(0.6, -0.55) + 0.25 * math.sin(t * 1.7),
                 cone=math.radians(16), cone_softness=math.radians(6))
    lights = [warm, cold, spot]
    apply_lighting(c, lights, occluders=mask, ambient=0.07, white=2.5)

    # Pillars drawn after lighting, shaded towards the warm light.
    for fx_, fy, r in pillars:
        px, py = fx_ * w, fy * h
        a = math.atan2(warm.y - py, warm.x - px)
        R.circle(c, px, py, r, R.radial_gradient(px + r * 0.5 * math.cos(a), py + r * 0.5 * math.sin(a),
                                                 r * 1.6, [(0, "#8a7f70"), (1, "#1e1b18")]))
    R.rect(c, int(0.85 * w), int(0.15 * h), 18, int(0.4 * h), "#2a2622")

    for light in lights:
        glow(c, light.x, light.y, w / 22, light.color, intensity=1.2)
        R.circle(c, light.x, light.y, max(2.0, w / 130), "#ffffff")
    bloom(c, threshold=0.8, sigma=w / 60, strength=0.7)
    vignette(c, strength=0.6)
    return c


def fountain(w: int, h: int, steps: int = 75, dt: float = 1 / 30, ps=None) -> tuple[Canvas, ParticleSystem]:
    solid = Canvas(w, h, mode="L", background=0)
    R.rect(solid, int(w * 0.18), int(h * 0.62), int(w * 0.26), 10, 255, aa=False)
    R.rect(solid, int(w * 0.6), int(h * 0.5), int(w * 0.22), 10, 255, aa=False)
    R.circle(solid, w * 0.5, h * 0.8, 22, 255, aa=False)
    mask = solid.pixels[:, :, 0] > 0
    if ps is None:
        ps = ParticleSystem(gravity=(0, 0.75 * h), bounds=(0, 0, w - 1, h - 1), colliders=mask,
                            restitution=0.55, friction=0.05, drag=0.15,
                            colors=[(0, "#fff6c8"), (0.25, "#ffb347"), (0.7, "#ff5e3a"), (1, "#5a1020")],
                            fade=[(0, 1), (0.8, 0.9), (1, 0)], seed=11)
        ps.add_emitter(Emitter(w * 0.5, h * 0.32, rate=700 * w / 540, angle=-math.pi / 2, spread=0.55,
                               speed=(0.33 * h, 0.6 * h), life=(1.6, 2.6), size=(0.8, 2.0), jitter=3))
    for _ in range(steps):
        ps.step(dt)
    c = Canvas(w, h, background="#0e0e16")
    c.blend(0, 0, mask, "#34344a")
    ps.render(c, mode="add")
    glow(c, w * 0.5, h * 0.32, 30, "#ffdd99", intensity=0.8)
    bloom(c, threshold=0.55, sigma=5, strength=0.9)
    return c, ps


def build_page1(doc: Document) -> None:
    page = doc.new_page(background=PAPER)
    c = page.canvas
    W, H = c.width, c.height
    m = 48
    inner = W - 2 * m

    title = "pixelpdf engine"
    draw_text(c, title, W // 2, m - 8, INK, scale=6, align="center",
              colors=lambda i: fx.hsv(0.02 + i * 0.045, 0.75, 0.85))
    draw_text(c, "every pixel below was computed in Python and stored losslessly",
              W // 2, m + 52, "#6b6b7b", scale=2, align="center")
    y = m + 92

    y = heading(c, "Primitives", m, y)
    panel = primitives_panel(inner, 150)
    c.blit(panel, m, y)
    y += panel.height + 24

    y = heading(c, "Text effects over time", m, y)
    strip = text_filmstrip(inner, 4)
    c.blit(strip, m + (inner - strip.width) // 2, y)
    y += strip.height + 16

    y = heading(c, "Spinners (four frames)", m, y)
    spin = spinner_filmstrip(inner, 4)
    c.blit(spin, m + (inner - spin.width) // 2, y)
    y += spin.height + 20

    y = heading(c, "Lighting and particles", m, y)
    half = (inner - 24) // 2
    ph = H - y - m
    c.blit(lit_scene(half, ph), m, y)
    c.blit(fountain(half, ph)[0], m + half + 24, y)


# -- page 2: an animation ----------------------------------------------------

def animation_frames(w: int, h: int, duration: float, fps: float):
    """Moving light + fountain + spinner + wave text, rendered frame by frame."""
    ps = None
    for t in frame_times(duration, fps):
        scene = lit_scene(w, h, t)
        sparks, ps = fountain(w // 2, h // 2, steps=1 if ps else 30, dt=1 / fps, ps=ps)
        scene.blit(sparks, w - sparks.width - 12, h - sparks.height - 12, opacity=0.95)
        R.rect(scene, 12, 12, 250, 70, "#101018", radius=12, opacity=0.75)
        spinners.arc_spinner(scene, 47, 47, 22, t, "#ffc27a", track="#3a3a4a")
        draw_text(scene, "LIVE", 82, 26, scale=3, offsets=fx.wave(t, amplitude=3), colors=fx.rainbow(t))
        draw_text(scene, f"t = {t:4.2f}s", 82, 60, "#c8c8d8")
        yield scene


def build_page2(doc: Document, frames: list[Canvas], fps: float) -> None:
    page = doc.new_page(background=PAPER)
    c = page.canvas
    W, H = c.width, c.height
    m = 48
    draw_text(c, "One animation, frame by frame", W // 2, m - 8, INK, scale=4, align="center")
    draw_text(c, f"{len(frames)} frames at {fps:g} fps, left to right, top to bottom. "
                 "Milestone 3 plays these as a flipbook.", W // 2, m + 40, "#6b6b7b", align="center")
    sheet = contact_sheet(frames, COLUMNS, gap=10, background=PAPER)
    c.blit(sheet, (W - sheet.width) // 2, m + 70)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="out/engine_showcase.pdf")
    parser.add_argument("--frames", metavar="DIR", help="also write the page-2 animation as PNGs")
    parser.add_argument("--fps", type=float, default=5)
    args = parser.parse_args()

    doc = Document(title="pixelpdf — engine showcase")
    build_page1(doc)
    fw = (doc.pages[0].canvas.width - 96 - 10 * (COLUMNS + 1)) // COLUMNS
    frames = list(animation_frames(fw, int(fw * 0.75), duration=3.0, fps=args.fps))
    build_page2(doc, frames, args.fps)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KiB)")
    if args.frames:
        paths = save_frames(frames, args.frames)
        print(f"wrote {len(paths)} frames to {args.frames}")


if __name__ == "__main__":
    main()
