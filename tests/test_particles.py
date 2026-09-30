import math

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.engine.particles import Emitter, ParticleSystem


def run(ps, steps, dt=1 / 30):
    for _ in range(steps):
        ps.step(dt)
    return ps


def test_emitter_rate_and_carry():
    ps = ParticleSystem(gravity=(0, 0), seed=1)
    ps.add_emitter(Emitter(0, 0, rate=45, life=(10, 10)))
    run(ps, 30)  # one second
    assert len(ps) == 45


def test_particles_expire():
    ps = ParticleSystem(gravity=(0, 0), seed=1)
    ps.emit(100, 50, 50, life=(0.5, 0.5))
    run(ps, 14)
    assert len(ps) == 100
    run(ps, 2)
    assert len(ps) == 0


def test_capacity_is_respected():
    ps = ParticleSystem(capacity=10, seed=1)
    ps.emit(50, 0, 0)
    assert len(ps) == 10


def test_gravity_accelerates():
    ps = ParticleSystem(gravity=(0, 100), seed=1)
    ps.emit(1, 0, 0, speed=(0, 0), life=(5, 5))
    run(ps, 10, dt=0.1)
    assert ps.vel[0, 1] == pytest.approx(100, rel=1e-4)
    assert ps.pos[0, 1] > 40


def test_drag_slows_down():
    ps = ParticleSystem(gravity=(0, 0), drag=1.0, seed=1)
    ps.emit(1, 0, 0, angle=0, spread=0, speed=(100, 100), life=(5, 5))
    run(ps, 10, dt=0.1)
    assert ps.vel[0, 0] == pytest.approx(100 * math.exp(-1), rel=1e-3)


def test_deterministic_with_seed():
    def sim(seed):
        ps = ParticleSystem(seed=seed)
        ps.add_emitter(Emitter(50, 50, rate=100))
        return run(ps, 20).pos.copy()

    np.testing.assert_array_equal(sim(3), sim(3))
    assert not np.array_equal(sim(3), sim(4))


def test_bounds_contain_particles():
    ps = ParticleSystem(gravity=(0, 500), bounds=(0, 0, 99, 99), restitution=0.8, seed=2)
    ps.emit(300, 50, 50, speed=(100, 400), life=(10, 10))
    run(ps, 120)
    assert len(ps) == 300
    assert (ps.pos >= 0).all() and (ps.pos <= 99).all()


def test_particles_bounce_off_collider_mask():
    solid = np.zeros((100, 100), bool)
    solid[60:, :] = True  # floor
    ps = ParticleSystem(gravity=(0, 400), colliders=solid, bounds=(0, 0, 99, 99),
                        restitution=0.5, seed=3)
    ps.emit(200, 50, 20, spread=math.pi, speed=(0, 80), life=(10, 10))
    run(ps, 90)
    assert len(ps) == 200
    assert (ps.pos[:, 1] < 60).all()


def test_ramps():
    ps = ParticleSystem(gravity=(0, 0), colors=[(0, "#000000"), (1, "#ffffff")],
                        fade=[(0, 1), (1, 0)], grow=[(0, 1), (1, 3)], seed=1)
    ps.emit(1, 0, 0, life=(2, 2), size=(2, 2))
    run(ps, 10, dt=0.1)
    colors, alpha, radius = ps.attributes()
    assert colors[0].tolist() == pytest.approx([127.5] * 3, abs=0.1)
    assert alpha[0] == pytest.approx(0.5, abs=1e-5)
    assert radius[0] == pytest.approx(4, abs=1e-4)


@pytest.mark.parametrize("mode", ["add", "normal"])
def test_render_draws_particles(mode):
    ps = ParticleSystem(gravity=(0, 0), colors=[(0, "#ff0000"), (1, "#ff0000")], seed=1)
    ps.emit(1, 10, 10, speed=(0, 0), size=(2, 2), life=(5, 5))
    c = Canvas(21, 21, background=0)
    ps.render(c, mode=mode)
    assert c.get_pixel(10, 10) == (255, 0, 0)
    assert c.get_pixel(0, 0) == (0, 0, 0)
    assert c.pixels[:, :, 0].astype(float).sum() / 255 == pytest.approx(math.pi * 4, rel=0.1)
