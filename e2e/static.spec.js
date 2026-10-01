// Pixel-exact static pages (Document / Composer.add_canvas).
const fs = require('fs');
const path = require('path');
const { test, expect, fixtures, FIXTURES } = require('./viewer');
const support = require('./support');

test.describe('static pages', () => {
  let f;
  test.beforeEach(async ({ viewer }) => {
    f = fixtures().static;
    await viewer.open(f.file, f.bg, f.width);
  });

  test('page is shown at one screen pixel per canvas pixel', async ({ viewer }) => {
    expect(viewer.scale).toBeCloseTo(1, 2);
  });

  test('flat colour blocks are reproduced exactly', async ({ viewer }) => {
    const s = await viewer.settle();
    for (const [name, block] of Object.entries(f.blocks)) {
      const [x, y, w, h] = viewer.rect(block.rect);
      const inner = [x + 3, y + 3, w - 6, h - 6];
      expect(s.find(block.rgb, 0, inner).n, `${name} block`).toBe(inner[2] * inner[3]);
    }
  });

  test('1-px checkerboard and noise keep their exact pixels', async ({ viewer }) => {
    const s = await viewer.settle();
    // Checkerboard: canvas pixel (x, y) is white when x + y is odd.
    const [cx, cy, cw, ch] = f.checker;
    let checkerOk = 0;
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) {
      const [sx, sy] = viewer.toScreen(cx + x, cy + y);
      const want = (x + y) % 2 ? 255 : 0;
      if (s.at(sx, sy).every((v) => v === want)) checkerOk++;
    }
    // Noise: compare with the source pixels written by the fixture builder.
    const noise = fs.readFileSync(path.join(FIXTURES, f.noise_file));
    const [nx, ny, nw, nh] = f.noise;
    let noiseOk = 0;
    for (let y = 0; y < nh; y++) for (let x = 0; x < nw; x++) {
      const [sx, sy] = viewer.toScreen(nx + x, ny + y);
      const i = (y * nw + x) * 3;
      const got = s.at(sx, sy);
      if (got[0] === noise[i] && got[1] === noise[i + 1] && got[2] === noise[i + 2]) noiseOk++;
    }
    const checkerFraction = checkerOk / (cw * ch);
    const noiseFraction = noiseOk / (nw * nh);
    test.info().annotations.push({ type: 'exact', description:
      `checkerboard ${(100 * checkerFraction).toFixed(2)}%, noise ${(100 * noiseFraction).toFixed(2)}%` });
    if (support[viewer.kind].exactPixels) {
      expect(checkerFraction).toBe(1);
      expect(noiseFraction).toBe(1);
    } else {
      expect(checkerFraction).toBeLessThan(1);
    }
  });
});
