"""Vectorised particle systems: emitters, forces, collisions, rendering.

All state lives in numpy arrays, and the random generator is seeded, so a
simulation stepped with the same dt sequence reproduces exactly (important
for rendering animation frames deterministically).

    ps = ParticleSystem(gravity=(0, 300), bounds=(0, 0, w, h), seed=1)
    ps.add_emitter(Emitter(x=100, y=300, rate=200, angle=-pi/2, spread=0.3))
    for frame in range(60):
        ps.step(1 / 30)
        ps.render(canvas)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .canvas import Canvas, parse_color

__all__ = ["Emitter", "ParticleSystem"]

Range = tuple[float, float]


@dataclass
class Emitter:
    x: float
    y: float
    rate: float = 100.0
    """Particles per second (fractional amounts carry over between steps)."""
    angle: float = -math.pi / 2
    """Mean launch direction in radians (screen coordinates: -pi/2 is up)."""
    spread: float = math.pi / 6
    """Half-width of the launch cone in radians."""
    speed: Range = (80.0, 160.0)
    life: Range = (1.0, 2.0)
    size: Range = (1.0, 2.5)
    jitter: float = 0.0
    """Random offset radius around (x, y) for new particles."""
    active: bool = True
    _carry: float = field(default=0.0, repr=False)


class ParticleSystem:
    def __init__(self, capacity: int = 20000, *, gravity: Sequence[float] = (0.0, 200.0),
                 wind: Sequence[float] = (0.0, 0.0), drag: float = 0.0,
                 bounds: Optional[tuple[float, float, float, float]] = None,
                 restitution: float = 0.5, friction: float = 0.1,
                 colliders: Optional[np.ndarray] = None,
                 colors: Sequence = ((0.0, (255, 255, 255)), (1.0, (255, 255, 255))),
                 fade: Sequence[tuple[float, float]] = ((0.0, 1.0), (0.7, 1.0), (1.0, 0.0)),
                 grow: Sequence[tuple[float, float]] = ((0.0, 1.0), (1.0, 1.0)),
                 kill_outside: bool = True, seed: int = 0):
        """
        gravity, wind: accelerations in px/s².  drag: velocity damping per second.
        bounds: (x0, y0, x1, y1) walls particles bounce off; None = open space.
        colliders: (H, W) bool mask of solid pixels particles bounce off.
        colors / fade / grow: ramps over normalised age 0..1 as (t, value)
        pairs, giving color, opacity and a size multiplier.
        """
        self.capacity = capacity
        self.gravity = np.asarray(gravity, dtype=np.float32)
        self.wind = np.asarray(wind, dtype=np.float32)
        self.drag = drag
        self.bounds = bounds
        self.restitution = restitution
        self.friction = friction
        self.colliders = None if colliders is None else np.asarray(colliders, dtype=bool)
        self.kill_outside = kill_outside
        self.rng = np.random.default_rng(seed)
        self.emitters: list[Emitter] = []
        self.time = 0.0

        self._color_t = np.array([c[0] for c in colors], dtype=np.float32)
        self._color_v = np.stack([parse_color(c[1], 3) for c in colors]).astype(np.float32)
        self._fade = np.asarray(fade, dtype=np.float32)
        self._grow = np.asarray(grow, dtype=np.float32)

        self.pos = np.zeros((0, 2), dtype=np.float32)
        self.vel = np.zeros((0, 2), dtype=np.float32)
        self.age = np.zeros(0, dtype=np.float32)
        self.life = np.zeros(0, dtype=np.float32)
        self.size = np.zeros(0, dtype=np.float32)

    def __len__(self) -> int:
        return len(self.age)

    def add_emitter(self, emitter: Emitter) -> Emitter:
        self.emitters.append(emitter)
        return emitter

    # -- spawning ------------------------------------------------------------

    def emit(self, n: int, x: float, y: float, *, angle: float = -math.pi / 2,
             spread: float = math.pi, speed: Range = (50.0, 150.0), life: Range = (1.0, 2.0),
             size: Range = (1.0, 2.0), jitter: float = 0.0) -> None:
        """Spawn `n` particles at (x, y) — a burst when called once."""
        n = min(int(n), self.capacity - len(self))
        if n <= 0:
            return
        rng = self.rng
        theta = angle + rng.uniform(-spread, spread, n)
        spd = rng.uniform(*speed, n)
        pos = np.column_stack([np.full(n, x), np.full(n, y)])
        if jitter > 0:
            a = rng.uniform(0, 2 * math.pi, n)
            rad = jitter * np.sqrt(rng.uniform(0, 1, n))
            pos += np.column_stack([np.cos(a) * rad, np.sin(a) * rad])
        self.pos = np.concatenate([self.pos, pos.astype(np.float32)])
        self.vel = np.concatenate([self.vel, np.column_stack(
            [np.cos(theta) * spd, np.sin(theta) * spd]).astype(np.float32)])
        self.age = np.concatenate([self.age, np.zeros(n, np.float32)])
        self.life = np.concatenate([self.life, rng.uniform(*life, n).astype(np.float32)])
        self.size = np.concatenate([self.size, rng.uniform(*size, n).astype(np.float32)])

    # -- simulation ----------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance by dt seconds: spawn from emitters, integrate, collide, expire."""
        for e in self.emitters:
            if not e.active:
                continue
            e._carry += e.rate * dt
            count = int(e._carry)
            e._carry -= count
            self.emit(count, e.x, e.y, angle=e.angle, spread=e.spread, speed=e.speed,
                      life=e.life, size=e.size, jitter=e.jitter)

        if len(self):
            self.vel += (self.gravity + self.wind) * dt
            if self.drag:
                self.vel *= math.exp(-self.drag * dt)
            old = self.pos.copy()
            self.pos += self.vel * dt
            if self.bounds is not None:
                self._collide_bounds()
            if self.colliders is not None:
                self._collide_mask(old)
            self.age += dt

            keep = self.age < self.life
            if self.kill_outside and self.colliders is not None:
                h, w = self.colliders.shape
                keep &= (self.pos[:, 0] > -50) & (self.pos[:, 0] < w + 50) & (self.pos[:, 1] < h + 50)
            if not keep.all():
                self._keep(keep)
        self.time += dt

    def _keep(self, keep: np.ndarray) -> None:
        self.pos, self.vel = self.pos[keep], self.vel[keep]
        self.age, self.life, self.size = self.age[keep], self.life[keep], self.size[keep]

    def _collide_bounds(self) -> None:
        x0, y0, x1, y1 = self.bounds
        e, f = self.restitution, 1.0 - self.friction
        for axis, lo, hi in ((0, x0, x1), (1, y0, y1)):
            p, v = self.pos[:, axis], self.vel[:, axis]
            other = self.vel[:, 1 - axis]
            low, high = p < lo, p > hi
            hit = low | high
            p[low] = 2 * lo - p[low]
            p[high] = 2 * hi - p[high]
            v[hit] *= -e
            other[hit] *= f
            np.clip(p, lo, hi, out=p)

    def _solid(self, pts: np.ndarray) -> np.ndarray:
        h, w = self.colliders.shape
        xi = np.round(pts[:, 0]).astype(int)
        yi = np.round(pts[:, 1]).astype(int)
        inside = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        solid = np.zeros(len(pts), dtype=bool)
        solid[inside] = self.colliders[yi[inside], xi[inside]]
        return solid

    def _collide_mask(self, old: np.ndarray) -> None:
        hit = self._solid(self.pos)
        if not hit.any():
            return
        idx = np.nonzero(hit)[0]
        e, f = self.restitution, 1.0 - self.friction
        start, end = old[idx], self.pos[idx]
        # Which axis did we cross? Try moving along x only, then y only.
        x_only = np.column_stack([end[:, 0], start[:, 1]])
        y_only = np.column_stack([start[:, 0], end[:, 1]])
        blocked_x = self._solid(x_only)
        blocked_y = self._solid(y_only)
        flip_x = blocked_x | (~blocked_x & ~blocked_y)
        flip_y = blocked_y | (~blocked_x & ~blocked_y)
        vel = self.vel[idx]
        vel[:, 0] = np.where(flip_x, -vel[:, 0] * e, vel[:, 0] * f)
        vel[:, 1] = np.where(flip_y, -vel[:, 1] * e, vel[:, 1] * f)
        self.vel[idx] = vel
        self.pos[idx] = start  # stay on the free side of the surface

    # -- rendering -----------------------------------------------------------

    def attributes(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Current (colors (N,3), opacity (N,), radius (N,)) from the age ramps."""
        t = np.clip(self.age / np.maximum(self.life, 1e-6), 0.0, 1.0)
        colors = np.stack([np.interp(t, self._color_t, self._color_v[:, c]) for c in range(3)], axis=1)
        opacity = np.interp(t, self._fade[:, 0], self._fade[:, 1])
        radius = self.size * np.interp(t, self._grow[:, 0], self._grow[:, 1])
        return colors.astype(np.float32), opacity.astype(np.float32), radius.astype(np.float32)

    def render(self, canvas: Canvas, *, mode: str = "add", opacity: float = 1.0) -> None:
        """Splat particles as anti-aliased discs.

        mode "add" sums light (sparks, fire, glows); "normal" blends
        colors by coverage (smoke, dust, confetti).
        """
        if not len(self):
            return
        colors, alpha, radius = self.attributes()
        alpha = alpha * opacity
        h, w = canvas.height, canvas.width
        color_acc = np.zeros((h, w, 3), dtype=np.float32)
        alpha_acc = np.zeros((h, w), dtype=np.float32)

        # Group by stamp size so each group is one vectorised splat.
        reach = np.ceil(radius + 0.5).astype(int)
        for r in np.unique(reach):
            sel = reach == r
            px, py = self.pos[sel, 0], self.pos[sel, 1]
            cx, cy = np.round(px).astype(int), np.round(py).astype(int)
            oy, ox = np.mgrid[-r:r + 1, -r:r + 1]
            ox, oy = ox.ravel(), oy.ravel()
            X = cx[:, None] + ox[None, :]
            Y = cy[:, None] + oy[None, :]
            dist = np.hypot(X - px[:, None], Y - py[:, None])
            cov = np.clip(radius[sel, None] + 0.5 - dist, 0.0, 1.0) * alpha[sel, None]
            ok = (X >= 0) & (X < w) & (Y >= 0) & (Y < h) & (cov > 0)
            Xo, Yo, co = X[ok], Y[ok], cov[ok]
            rgb = np.broadcast_to(colors[sel][:, None, :], X.shape + (3,))[ok]
            np.add.at(alpha_acc, (Yo, Xo), co)
            np.add.at(color_acc, (Yo, Xo), rgb * co[:, None])

        covered = alpha_acc > 0
        if canvas.channels == 1:
            color_acc = color_acc.mean(axis=2, keepdims=True)
        if mode == "add":
            canvas.blend(0, 0, covered.astype(np.float32), color_acc, mode="add")
        else:
            mean = color_acc / np.maximum(alpha_acc, 1e-6)[:, :, None]
            canvas.blend(0, 0, np.clip(alpha_acc, 0.0, 1.0), mean, mode=mode)
