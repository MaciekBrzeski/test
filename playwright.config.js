// Browser end-to-end tests. Three projects run the same specs:
//
//   chromium  Chrome's built-in PDF viewer (PDFium)
//   pdfjs     pdf.js, the PDF engine inside Firefox, hosted in Chromium
//             (e2e/pdfjs/viewer.html) with forms and scripting enabled
//   firefox   Firefox's own PDF viewer; needs `npx playwright install firefox`
//             and is reported as skipped when that browser is missing
//
// Every project views pages at 150% zoom with a device scale factor of 1, so
// one canvas pixel of a 144 DPI page is exactly one screen pixel.
const fs = require('fs');
const { defineConfig } = require('@playwright/test');

const CHROMIUM = process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const chromiumLaunch = {
  executablePath: fs.existsSync(CHROMIUM) ? CHROMIUM : undefined,
  // The full browser in new headless mode includes the PDF viewer
  // (Playwright's default headless shell does not).
  args: ['--headless=new', '--disable-background-networking', '--disable-component-update',
         '--no-first-run'],
};

function firefoxInstalled() {
  try {
    return fs.existsSync(require('playwright-core').firefox.executablePath());
  } catch (e) {
    return false;
  }
}

const FIREFOX = firefoxInstalled();

module.exports = defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: 2,
  reporter: [['list']],
  globalSetup: require.resolve('./e2e/global-setup.js'),
  webServer: {
    command: 'node e2e/server.js 8123',
    url: 'http://127.0.0.1:8123/e2e/pdfjs/viewer.html',
    reuseExistingServer: true,
  },
  use: {
    viewport: { width: 1280, height: 1800 },
    deviceScaleFactor: 1,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', metadata: { viewer: 'pdfium', available: true },
      use: { browserName: 'chromium', launchOptions: chromiumLaunch } },
    { name: 'pdfjs', metadata: { viewer: 'pdfjs', available: true },
      use: { browserName: 'chromium', launchOptions: chromiumLaunch } },
    FIREFOX
      ? { name: 'firefox', metadata: { viewer: 'firefox', available: true },
          use: { browserName: 'firefox', launchOptions: { firefoxUserPrefs: {
            'pdfjs.disabled': false, 'pdfjs.enableScripting': true,
            'browser.download.open_pdf_attachments_inline': true } } } }
      // Not installed: every test is reported as skipped (see e2e/viewer.js).
      // Playwright still starts a browser for each worker, so give it one that
      // exists; no test body runs in it.
      : { name: 'firefox', metadata: { viewer: 'firefox', available: false },
          use: { browserName: 'chromium', launchOptions: chromiumLaunch } },
  ],
});
