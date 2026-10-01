// Shared helpers: open a fixture PDF in the project's viewer, take and
// analyse screenshots, and convert canvas pixel coordinates (as used by
// pixelpdf) to screen coordinates.
'use strict';
const fs = require('fs');
const path = require('path');
const { PNG } = require('pngjs');
const base = require('@playwright/test');

const FIXTURES = path.resolve(__dirname, '.fixtures');
const PORT = 8123;
const ZOOM = 150;  // percent; with a 144 DPI page, 1 canvas px = 1 screen px

function fixtures() {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, 'fixtures.json'), 'utf8'));
}

class Shot {
  constructor(png) {
    const img = PNG.sync.read(png);
    this.width = img.width;
    this.height = img.height;
    this.data = img.data;
  }

  at(x, y) {
    const i = (Math.round(y) * this.width + Math.round(x)) * 4;
    return [this.data[i], this.data[i + 1], this.data[i + 2]];
  }

  // Bounding box and count of pixels within `tol` of `rgb`, inside an
  // optional screen rect [x, y, w, h].
  find(rgb, tol = 3, rect = null) {
    const [rx, ry, rw, rh] = rect || [0, 0, this.width, this.height];
    let n = 0, sx = 0, sy = 0, x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1;
    for (let y = Math.max(0, ry); y < Math.min(this.height, ry + rh); y++) {
      for (let x = Math.max(0, rx); x < Math.min(this.width, rx + rw); x++) {
        const i = (y * this.width + x) * 4;
        if (Math.abs(this.data[i] - rgb[0]) <= tol && Math.abs(this.data[i + 1] - rgb[1]) <= tol &&
            Math.abs(this.data[i + 2] - rgb[2]) <= tol) {
          n++; sx += x; sy += y;
          if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
        }
      }
    }
    return n ? { n, cx: sx / n, cy: sy / n, box: [x0, y0, x1 - x0 + 1, y1 - y0 + 1] } : { n: 0 };
  }

  // Number of pixels that differ by more than `tol` in any channel.
  diff(other, rect = null, tol = 24) {
    const [rx, ry, rw, rh] = rect || [0, 0, this.width, this.height];
    let changed = 0;
    for (let y = Math.max(0, ry); y < Math.min(this.height, ry + rh); y++) {
      for (let x = Math.max(0, rx); x < Math.min(this.width, rx + rw); x++) {
        const i = (y * this.width + x) * 4;
        if (Math.abs(this.data[i] - other.data[i]) > tol || Math.abs(this.data[i + 1] - other.data[i + 1]) > tol ||
            Math.abs(this.data[i + 2] - other.data[i + 2]) > tol) changed++;
      }
    }
    return changed;
  }

  // Pixels whose colour is far from grey (saturation proxy), inside rect.
  colourful(rect, minSpread = 60) {
    const [rx, ry, rw, rh] = rect;
    let n = 0;
    for (let y = Math.max(0, ry); y < Math.min(this.height, ry + rh); y++) {
      for (let x = Math.max(0, rx); x < Math.min(this.width, rx + rw); x++) {
        const i = (y * this.width + x) * 4;
        const r = this.data[i], g = this.data[i + 1], b = this.data[i + 2];
        if (Math.max(r, g, b) - Math.min(r, g, b) >= minSpread) n++;
      }
    }
    return n;
  }
}

class Viewer {
  constructor(page, kind) {
    this.page = page;
    this.kind = kind;            // 'pdfium' | 'pdfjs' | 'firefox'
    this.origin = null;          // screen position of the page's canvas pixel (0, 0)
    this.scale = 1;
  }

  url(file) {
    const abs = path.join(FIXTURES, file);
    if (this.kind === 'pdfjs') {
      return `http://127.0.0.1:${PORT}/e2e/pdfjs/viewer.html?file=/e2e/.fixtures/${file}&zoom=${ZOOM / 100}`;
    }
    const hash = this.kind === 'pdfium' ? `#toolbar=0&zoom=${ZOOM}` : `#zoom=${ZOOM}`;
    return `file://${abs}${hash}`;
  }

  // Open `file` and wait until the page with background `bg` is rendered
  // and the screen has settled; locates the page for coordinate mapping.
  async open(file, bg, canvasWidth) {
    await this.page.goto(this.url(file));
    await this.locate(bg, canvasWidth);
  }

  async shot() {
    return new Shot(await this.page.screenshot());
  }

  // Screenshot repeatedly until two consecutive ones agree (or time runs out).
  async settle(timeout = 8000, region = null) {
    const end = Date.now() + timeout;
    let prev = await this.shot();
    while (Date.now() < end) {
      await this.page.waitForTimeout(250);
      const next = await this.shot();
      if (next.diff(prev, region, 2) === 0) return next;
      prev = next;
    }
    return prev;
  }

  // Find the topmost fully visible page whose background is `bg`, using the
  // magenta markers the fixture builder paints in both top corners. Viewers
  // may draw a border over the page's outermost pixels, so only the markers'
  // inner edges are used: the left marker's right/bottom edge gives the
  // origin, the gap between the two markers' inner edges the scale.
  async locate(bg, canvasWidth, timeout = 15000) {
    // Viewers lay a page out more than once while loading (Chrome applies
    // #zoom after a first layout), so accept a position only when two
    // consecutive screenshots agree on it.
    const end = Date.now() + timeout;
    let last = null;
    while (Date.now() < end) {
      const found = await this._locateOnce(bg, canvasWidth);
      if (found) {
        const key = `${found.origin.map((v) => v.toFixed(2))}|${found.scale.toFixed(5)}`;
        if (key === last) {
          this.origin = found.origin;
          this.scale = found.scale;
          return found.shot;
        }
        last = key;
      } else {
        last = null;
      }
      await this.page.waitForTimeout(300);
    }
    throw new Error(`page with background ${bg} and corner markers did not appear`);
  }

  async _locateOnce(bg, canvasWidth) {
    const marker = fixtures().marker;
    {
      const s = await this.shot();
      if (s.find(bg, 2).n > 20000) {
        const marks = s.find(marker.rgb, 8);
        if (marks.n) {
          // Markers of the topmost visible page: rows near the first marker row.
          const top = marks.box[1];
          const band = [0, top, s.width, marker.size * 2];
          const row = s.find(marker.rgb, 8, band);
          const [x0, , w] = row.box;
          if (w > canvasWidth / 2) {
            const left = s.find(marker.rgb, 8, [x0, top, marker.size * 2, marker.size * 2]);
            const right = s.find(marker.rgb, 8, [x0 + w - marker.size * 2, top, marker.size * 2, marker.size * 2]);
            const innerLeft = left.box[0] + left.box[2];      // screen x of canvas x = size
            const innerRight = right.box[0];                  // screen x of canvas x = width - size
            const bottom = left.box[1] + left.box[3];         // screen y of canvas y = size
            const scale = (innerRight - innerLeft) / (canvasWidth - 2 * marker.size);
            return { shot: s, scale,
                     origin: [innerLeft - marker.size * scale, bottom - marker.size * scale] };
          }
        }
      }
    }
    return null;
  }

  toScreen(x, y) {
    return [this.origin[0] + x * this.scale, this.origin[1] + y * this.scale];
  }

  rect(r) {
    const [x, y] = this.toScreen(r[0], r[1]);
    return [Math.round(x), Math.round(y), Math.round(r[2] * this.scale), Math.round(r[3] * this.scale)];
  }

  async click(x, y) {
    const [sx, sy] = this.toScreen(x, y);
    await this.page.mouse.click(sx, sy);
  }

  // Click a text field (canvas rect), type, then click an empty spot of the
  // page so the field loses focus and its caret stops blinking.
  async typeInto(rect, text, blurAt = [20, 20]) {
    await this.click(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2);
    await this.page.waitForTimeout(150);
    await this.page.keyboard.type(text, { delay: 30 });
    await this.page.waitForTimeout(150);
    await this.click(...blurAt);
    await this.page.waitForTimeout(250);
  }

  // Pixels that change inside screen `rect` over `ms` milliseconds.
  async changesIn(rect, ms) {
    const a = await this.shot();
    await this.page.waitForTimeout(ms);
    return (await this.shot()).diff(a, rect);
  }

  // Type `key` into a field and wait for `reacted()` to confirm it arrived.
  // Under load a keystroke can land before the viewer has focused the
  // field and be lost; it is then typed again (up to `attempts` times).
  async sendKey(fieldRect, key, reacted, attempts = 3) {
    for (let i = 0; i < attempts; i++) {
      await this.typeInto(fieldRect, key);
      if (await reacted()) return true;
    }
    return false;
  }

  async hold(rect, ms) {
    const [sx, sy] = this.toScreen(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2);
    await this.page.mouse.move(sx, sy);
    await this.page.mouse.down();
    await this.page.waitForTimeout(ms);
    await this.page.mouse.up();
  }

  async scrollBy(dy) {
    const [sx, sy] = this.toScreen(600, 600);
    await this.page.mouse.move(sx, sy);
    await this.page.mouse.wheel(0, dy);
  }
}

const test = base.test.extend({
  // Browsers that aren't installed are reported as skipped, not failed. An
  // auto fixture runs for every test, before `page` is created.
  skipUnavailable: [async ({}, use, testInfo) => {
    testInfo.skip(!testInfo.project.metadata.available,
                  `${testInfo.project.name} is not installed (npx playwright install ${testInfo.project.name})`);
    await use();
  }, { auto: true }],
  viewer: async ({ page }, use, testInfo) => {
    await use(new Viewer(page, testInfo.project.metadata.viewer));
  },
});

module.exports = { test, expect: base.expect, fixtures, FIXTURES, Viewer, Shot };
