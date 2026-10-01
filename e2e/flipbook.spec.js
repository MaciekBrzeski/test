// Flipbook PDFs: one page per frame, /Dur and /Trans on each page.
const { test, expect, fixtures } = require('./viewer');
const support = require('./support');

test.describe('flipbook', () => {
  let f;
  test.beforeEach(async ({ viewer }) => {
    f = fixtures().flipbook;
    await viewer.open(f.file, f.frames[0], f.width);
  });

  test('the first frame renders as drawn', async ({ viewer }) => {
    const s = await viewer.settle();
    const [x, y, w, h] = viewer.rect(f.squares[0]);
    const inner = [x + 3, y + 3, w - 6, h - 6];
    expect(s.find([255, 255, 255], 0, inner).n).toBe(inner[2] * inner[3]);
  });

  test('frames advance by themselves only where supported', async ({ viewer }) => {
    const before = await viewer.settle();
    // Six frames at 4 fps would all have played after 1.5 s; wait twice that.
    await viewer.page.waitForTimeout(3000);
    const after = await viewer.shot();
    const changed = after.diff(before);
    if (support[viewer.kind].autoAdvance) expect(changed).toBeGreaterThan(10000);
    else expect(changed).toBe(0);
  });

  test('scrolling shows every frame in order', async ({ viewer }) => {
    for (let i = 1; i < f.frames.length; i++) {
      await expect.poll(async () => {
        await viewer.scrollBy(400);
        const s = await viewer.shot();
        return s.find(f.frames[i], 0).n;
      }, { message: `frame ${i + 1} becomes visible`, timeout: 15000 }).toBeGreaterThan(200000);
    }
  });
});
