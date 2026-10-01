// Composer documents: links between pages, games that sleep off-page.
const { test, expect, fixtures } = require('./viewer');
const support = require('./support');

test.describe('composed documents', () => {
  let f;
  test.beforeEach(async ({ viewer }) => {
    f = fixtures().compose;
    await viewer.open(f.file, f.cover_bg, f.width);
    await viewer.settle();
  });

  async function followLink(viewer) {
    await viewer.click(f.link[0] + f.link[2] / 2, f.link[1] + f.link[3] / 2);
    // Landed when the game page's background fills the top of the screen.
    await expect.poll(async () => (await viewer.shot()).find(f.game_bg, 2, [0, 0, 1280, 300]).n,
                      { timeout: 10000 }).toBeGreaterThan(50000);
    await viewer.locate(f.game_bg, f.width);
  }

  function barPixels(viewer, shot) {
    return shot.find(f.bar, 30, viewer.rect(f.display)).n;
  }

  test('a link jumps to its target page', async ({ viewer }) => {
    if (!support[viewer.kind].links) test.skip();
    await followLink(viewer);
  });

  test('a game sleeps while its page is not in view', async ({ viewer }) => {
    // Three seconds on the cover = 90 frames = 9 bar cells if the game ran.
    await viewer.page.waitForTimeout(3000);
    await followLink(viewer);
    const arrived = barPixels(viewer, await viewer.shot());
    await viewer.page.waitForTimeout(3000);
    const later = barPixels(viewer, await viewer.shot());
    const cellPixels = later / Math.max(1, Math.round(later / (f.cell * f.cell * 0.5)));
    test.info().annotations.push({ type: 'bar', description: `arrived ${arrived}px, later ${later}px` });
    expect(later, 'the game runs on its own page').toBeGreaterThan(arrived);
    if (support[viewer.kind].sleepsOffPage) {
      // On arrival it can only have run for the second or so since the jump.
      expect(arrived).toBeLessThan(later / 2);
    } else {
      expect(arrived).toBeGreaterThan(cellPixels * 6);
    }
  });
});
