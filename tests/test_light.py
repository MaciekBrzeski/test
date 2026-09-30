import math

import numpy as np
import pytest

from pixelpdf import Canvas
from pixelpdf.engine.filters import box_blur, gaussian_blur, resize_bilinear, smoothstep
from pixelpdf.engine.light import (Light, apply_lighting, bloom, glow, light_map, tonemap,
                                   vignette)


def test_no_lights_gives_ambient():
    lm = light_map(20, 10, [], ambient=0.25)
    assert lm.shape == (10, 20, 3)
    np.testing.assert_allclose(lm, 0.25)


def test_point_light_falloff_is_radial():
    lm = light_map(101, 101, [Light(50, 50, radius=40)], ambient=0, scale=1)[:, :, 0]
    assert lm[50, 50] == pytest.approx(1.0)
    assert lm[50, 70] == pytest.approx(lm[70, 50], abs=1e-5)
    assert lm[50, 60] > lm[50, 70] > lm[50, 85]
    assert lm[50, 91] == 0  # beyond radius


def test_light_color():
    lm = light_map(21, 21, [Light(10, 10, color="#ff0000", radius=30)], ambient=0, scale=1)
    assert lm[10, 10].tolist() == pytest.approx([1, 0, 0])


def test_spot_light_cone():
    spot = Light(50, 50, radius=60, direction=0.0, cone=math.radians(20))
    lm = light_map(101, 101, [spot], ambient=0, scale=1)[:, :, 0]
    assert lm[50, 80] > 0.5    # straight ahead
    assert lm[50, 20] == 0     # behind
    assert lm[20, 50] == 0     # 90 degrees off-axis


def test_occluder_casts_shadow():
    occ = np.zeros((60, 120), bool)
    occ[20:40, 50:55] = True  # wall to the right of the light
    lm = light_map(120, 60, [Light(20, 30, radius=150)], occluders=occ, ambient=0, scale=1)[:, :, 0]
    assert lm[30, 45] > 0.5      # in front of the wall: lit
    assert lm[30, 90] == 0       # directly behind it: shadowed
    assert lm[2, 70] > 0         # outside the shadow wedge: lit


def test_soft_shadow_has_penumbra():
    occ = np.zeros((60, 120), bool)
    occ[20:40, 50:55] = True
    hard = light_map(120, 60, [Light(20, 30, radius=150)], occluders=occ, ambient=0, scale=1)
    soft = light_map(120, 60, [Light(20, 30, radius=150, shadow_softness=0.3)],
                     occluders=occ, ambient=0, scale=1)
    edge_hard = np.unique(np.round(hard[:, 100, 0], 2))
    edge_soft = np.unique(np.round(soft[:, 100, 0], 2))
    assert len(edge_soft) > len(edge_hard)


def test_low_res_light_map_is_close_to_full_res():
    lights = [Light(40, 30, radius=50)]
    full = light_map(80, 60, lights, scale=1)
    half = light_map(80, 60, lights, scale=0.5)
    assert np.abs(full - half).mean() < 0.02


def test_apply_lighting_multiplies():
    c = Canvas(10, 10, background=200)
    apply_lighting(c, [], ambient=0.5)
    assert c.get_pixel(0, 0) == (100, 100, 100)
    g = Canvas(10, 10, mode="L", background=200)
    apply_lighting(g, [], ambient=0.5)
    assert g.get_pixel(0, 0) == (100,)


def test_glow_adds_light():
    c = Canvas(41, 41, background=0)
    glow(c, 20, 20, 15, "#ffffff")
    assert c.get_pixel(20, 20) == (255, 255, 255)
    assert c.get_pixel(0, 0) == (0, 0, 0)
    assert c.get_pixel(20, 30)[0] < 255


def test_bloom_spreads_bright_pixels_only():
    c = Canvas(41, 41, background=20)
    c.fill_rect(18, 18, 5, 5, 255)
    bloom(c, threshold=0.7, sigma=3)
    assert c.get_pixel(20, 25)[0] > 20      # halo next to the bright square
    assert c.get_pixel(0, 0)[0] == 20       # far away: untouched


def test_vignette_darkens_corners_only():
    c = Canvas(101, 101, background=200)
    vignette(c, strength=0.8)
    assert c.get_pixel(50, 50) == (200, 200, 200)
    assert c.get_pixel(0, 0)[0] < 100


def test_filters():
    const = np.full((20, 30, 3), 0.4, np.float32)
    np.testing.assert_allclose(box_blur(const, 3), 0.4, atol=1e-6)
    np.testing.assert_allclose(gaussian_blur(const, 5), 0.4, atol=1e-6)
    impulse = np.zeros((31, 31), np.float32)
    impulse[15, 15] = 1
    blurred = gaussian_blur(impulse, 3)
    assert blurred.sum() == pytest.approx(1, abs=1e-4)
    assert blurred[15, 15] == blurred.max()
    np.testing.assert_allclose(blurred, blurred.T, atol=1e-6)
    ramp = np.tile(np.arange(10, dtype=np.float32), (4, 1))
    np.testing.assert_allclose(resize_bilinear(ramp, 4, 10), ramp)
    assert resize_bilinear(ramp, 8, 20).shape == (8, 20)
    assert smoothstep(0, 1, 0.5) == pytest.approx(0.5)


def test_tonemap_curve():
    lm = np.array([0.0, 0.5, 1.0, 2.0, 8.0], np.float32)
    out = tonemap(lm, white=2.0)
    assert out[0] == 0 and out[3] == pytest.approx(1.0)
    assert (np.diff(out) > 0).all()          # monotonic
    assert out[-1] > 1                         # beyond white still clips later
    assert tonemap(np.float32(1.0), white=1.0) == pytest.approx(1.0)


def test_apply_lighting_with_tonemap_keeps_highlights_below_clipping():
    c = Canvas(41, 41, background=200)
    apply_lighting(c, [Light(20, 20, radius=60, intensity=1.5)], ambient=0.1, white=3.0, scale=1)
    assert c.get_pixel(20, 20)[0] < 255
