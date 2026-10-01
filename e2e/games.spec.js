// Interactive pages: JavaScript games drawing on comb-field displays.
const { test, expect, fixtures } = require('./viewer');
const support = require('./support');

function onlyIf(viewer, feature) {
  test.info().annotations.push({ type: 'expects', description: `${feature}=${support[viewer.kind][feature]}` });
  return support[viewer.kind][feature];
}

test.describe('games', () => {
  test('fireworks animate by themselves and update the HUD', async ({ viewer }) => {
    const g = fixtures().games.fireworks;
    await viewer.open(g.file, g.bg, g.width);
    const first = await viewer.shot();
    if (!onlyIf(viewer, 'scripting')) {
      await viewer.page.waitForTimeout(3000);
      expect((await viewer.shot()).diff(first, viewer.rect(g.display))).toBe(0);
      return;
    }
    // Rockets rise from the start; the spark counter only changes once the
    // first one bursts (about 2 s in), so wait for each rather than sampling.
    await expect.poll(async () => (await viewer.changesIn(viewer.rect(g.display), 500)),
                      { message: 'display animates', timeout: 8000 }).toBeGreaterThan(50);
    await expect.poll(async () => (await viewer.shot()).diff(first, viewer.rect(g.huds.count)),
                      { message: 'spark counter changes', timeout: 8000 }).toBeGreaterThan(0);
  });

  test('display cells line up with the layout', async ({ viewer }) => {
    const g = fixtures().geometry;
    await viewer.open(g.file, g.bg, g.width);
    const s = await viewer.settle();
    for (const [col, row, rgb] of g.cells) {
      const cell = [g.display[0] + col * g.cell, g.display[1] + row * g.cell, g.cell, g.cell];
      const hit = s.find(rgb, 40, viewer.rect([cell[0] - g.cell, cell[1] - g.cell, 3 * g.cell, 3 * g.cell]));
      if (!onlyIf(viewer, 'scripting')) { expect(hit.n).toBe(0); continue; }
      expect(hit.n, `cell ${col},${row} is lit`).toBeGreaterThan(20);
      const [cx, cy] = viewer.toScreen(cell[0] + g.cell / 2, cell[1] + g.cell / 2);
      // The glyph's centre sits within a quarter cell of the cell's centre.
      expect(Math.abs(hit.cx - cx), `cell ${col},${row} x`).toBeLessThan(g.cell * viewer.scale / 4);
      expect(Math.abs(hit.cy - cy), `cell ${col},${row} y`).toBeLessThan(g.cell * viewer.scale / 4);
      // ...and stays inside its cell.
      const [bx, by, bw, bh] = hit.box;
      const [sx, sy, sw, sh] = viewer.rect(cell);
      expect(bx).toBeGreaterThanOrEqual(sx - 1);
      expect(by).toBeGreaterThanOrEqual(sy - 1);
      expect(bx + bw).toBeLessThanOrEqual(sx + sw + 1);
      expect(by + bh).toBeLessThanOrEqual(sy + sh + 1);
    }
  });

  test('typed keys steer the snake, and P pauses it', async ({ viewer }) => {
    const g = fixtures().games.snake;
    await viewer.open(g.file, g.bg, g.width);
    const display = viewer.rect(g.display);
    const idle = await viewer.settle(8000, display);
    await viewer.page.waitForTimeout(600);
    expect((await viewer.shot()).diff(idle, display), 'nothing moves before a key').toBe(0);

    const started = await viewer.sendKey(g.keys, 'd', async () => (await viewer.changesIn(display, 600)) > 0);
    if (!onlyIf(viewer, 'keys')) { expect(started).toBe(false); return; }
    expect(started, 'D starts the snake').toBe(true);

    const paused = await viewer.sendKey(g.keys, 'p', async () => (await viewer.changesIn(display, 600)) === 0);
    expect(paused, 'P freezes it').toBe(true);
    // Frozen because paused, not because the snake crashed: no GAME OVER text.
    expect((await viewer.shot()).find([255, 230, 109], 30, display).n).toBe(0);
  });

  test('holding an on-screen button moves the breakout paddle', async ({ viewer }) => {
    const g = fixtures().games.breakout;
    await viewer.open(g.file, g.bg, g.width);
    const display = viewer.rect(g.display);
    const before = await viewer.settle(8000, display);
    const right = g.buttons.find((btn) => btn.key === 'd');
    // Retry like sendKey: under load the first press can be lost.
    let moved = 0;
    for (let attempt = 0; attempt < 3 && moved === 0; attempt++) {
      await viewer.hold(right.rect, 700);
      await viewer.page.waitForTimeout(300);
      moved = (await viewer.shot()).diff(before, display);
      await test.info().attach(`after-hold-${attempt + 1}`, { body: await viewer.page.screenshot(),
                                                              contentType: 'image/png' });
    }
    if (onlyIf(viewer, 'buttons')) expect(moved).toBeGreaterThan(0);
    else expect(moved).toBe(0);
  });

  test('on-screen buttons are drawn', async ({ viewer }) => {
    const g = fixtures().games.breakout;
    await viewer.open(g.file, g.bg, g.width);
    const s = await viewer.settle(8000);
    for (const btn of g.buttons) {
      // Button face colour #3a3a4a fills most of the button.
      const r = viewer.rect(btn.rect);
      expect(s.find([58, 58, 74], 6, r).n, `button "${btn.label}"`).toBeGreaterThan(r[2] * r[3] * 0.5);
    }
  });
});
