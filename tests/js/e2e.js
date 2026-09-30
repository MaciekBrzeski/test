// End-to-end check of an interactive PDF in Chromium's built-in PDF viewer.
//
//   node e2e.js <pdf> <scenario> <outdir> <chromium> <playwright>
//
// Scenarios:
//   animate  two screenshots 700 ms apart must differ (the game runs by itself)
//   keys     idle -> type "d" -> type "p": reports how much the screen changed
//            in each phase (expects idle 0, moving > 0, paused 0)
// Prints one JSON line with the measurements.
'use strict';
const path = require('path');
const [pdf, scenario, outdir, chromiumPath, playwrightPath] = process.argv.slice(2);
const { chromium } = require(playwrightPath);

const KEY_BOX = [255, 248, 208];  // background of the key capture field

(async () => {
  const browser = await chromium.launch({ executablePath: chromiumPath, headless: true,
                                          args: ['--headless=new', '--disable-background-networking',
                                                  '--disable-component-update', '--no-first-run'] });
  const viewer = await browser.newPage({ viewport: { width: 900, height: 1300 } });
  const scratch = await browser.newPage();
  await viewer.goto('file://' + pdf + '#toolbar=0&view=FitH');
  await viewer.waitForTimeout(1500);

  // Screenshots are decoded and compared inside a blank tab, so only small
  // results travel back to node.
  let shots = 0;
  async function shot() {
    const id = shots++;
    const png = await viewer.screenshot({ path: path.join(outdir, `shot${id}.png`) });
    await scratch.evaluate(async ([b64, id]) => {
      const img = new Image();
      img.src = 'data:image/png;base64,' + b64;
      await img.decode();
      const c = document.createElement('canvas');
      c.width = img.width; c.height = img.height;
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0);
      window.shots = window.shots || {};
      window.shots[id] = ctx.getImageData(0, 0, img.width, img.height);
    }, [png.toString('base64'), id]);
    return id;
  }

  function diff(a, b) {
    return scratch.evaluate(([a, b]) => {
      const A = window.shots[a].data, B = window.shots[b].data;
      let changed = 0, colored = 0;
      for (let i = 0; i < A.length; i += 4) {
        const d = Math.max(Math.abs(A[i] - B[i]), Math.abs(A[i + 1] - B[i + 1]), Math.abs(A[i + 2] - B[i + 2]));
        if (d > 24) {
          changed++;
          if (Math.max(B[i], B[i + 1], B[i + 2]) - Math.min(B[i], B[i + 1], B[i + 2]) > 60) colored++;
        }
      }
      return { changed, colored };
    }, [a, b]);
  }

  async function find(id, rgb) {
    const hit = await scratch.evaluate(([id, rgb]) => {
      const img = window.shots[id];
      let sx = 0, sy = 0, n = 0;
      for (let y = 0; y < img.height; y++) for (let x = 0; x < img.width; x++) {
        const i = (y * img.width + x) * 4;
        if (Math.abs(img.data[i] - rgb[0]) < 6 && Math.abs(img.data[i + 1] - rgb[1]) < 6 &&
            Math.abs(img.data[i + 2] - rgb[2]) < 6) { sx += x; sy += y; n++; }
      }
      return [sx / n, sy / n, n];
    }, [id, rgb]);
    if (hit[2] < 50) throw new Error('key capture field not found on screen');
    return hit;
  }

  async function type(img, key) {
    const [x, y] = await find(img, KEY_BOX);
    await viewer.mouse.click(x, y);
    await viewer.keyboard.type(key);
    await viewer.waitForTimeout(100);
    await viewer.mouse.click(10, 10);  // blur, so the text cursor stops blinking
    await viewer.waitForTimeout(300);
  }

  const result = {};
  if (scenario === 'animate') {
    const a = await shot();
    await viewer.waitForTimeout(700);
    const b = await shot();
    Object.assign(result, await diff(a, b));
  } else if (scenario === 'keys') {
    // Under load the first frames and field text can take a while to appear;
    // start measuring only once two consecutive screenshots agree.
    let a = await shot();
    for (let tries = 0; tries < 20; tries++) {
      await viewer.waitForTimeout(300);
      const next = await shot();
      const settled = (await diff(a, next)).changed === 0;
      a = next;
      if (settled) break;
    }
    await viewer.waitForTimeout(600);
    const b = await shot();
    result.idle_changed = (await diff(a, b)).changed;
    await type(b, 'd');
    const c = await shot();
    await viewer.waitForTimeout(600);
    const d = await shot();
    result.moving_changed = (await diff(c, d)).changed;
    await type(d, 'p');
    const e = await shot();
    await viewer.waitForTimeout(600);
    const f = await shot();
    result.paused_changed = (await diff(e, f)).changed;
  } else if (scenario.startsWith('link:')) {
    // link:<json> with {bg: [r,g,b], width: canvas px, click: [x, y] canvas px}.
    // Finds the page on screen by its background colour, clicks the given
    // point (a link), then checks that the page we land on animates.
    const spec = JSON.parse(scenario.slice(5));
    const a = await shot();
    const box = await scratch.evaluate(([id, rgb]) => {
      const img = window.shots[id];
      let x0 = 1e9, y0 = 1e9, x1 = -1;
      for (let y = 0; y < img.height; y++) for (let x = 0; x < img.width; x++) {
        const i = (y * img.width + x) * 4;
        if (Math.abs(img.data[i] - rgb[0]) < 4 && Math.abs(img.data[i + 1] - rgb[1]) < 4 &&
            Math.abs(img.data[i + 2] - rgb[2]) < 4) {
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y);
        }
      }
      return [x0, y0, x1];
    }, [a, spec.bg]);
    const scale = (box[2] - box[0] + 1) / spec.width;
    await viewer.mouse.click(box[0] + spec.click[0] * scale, box[1] + spec.click[1] * scale);
    await viewer.waitForTimeout(1500);
    const b = await shot();
    result.jumped = (await diff(a, b)).changed;
    await viewer.waitForTimeout(700);
    const c = await shot();
    Object.assign(result, await diff(b, c));
  } else {
    throw new Error('unknown scenario ' + scenario);
  }
  await browser.close();
  console.log(JSON.stringify(result));
})().catch((e) => { console.error(e); process.exit(1); });
