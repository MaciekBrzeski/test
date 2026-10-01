// What each viewer is expected to do. The specs assert these both ways:
// a feature marked false must observably *not* happen (e.g. no auto-advance),
// so this table can't silently drift from reality.
//
// pdfium:  Chrome / Edge built-in viewer
// pdfjs:   pdf.js (Firefox's engine) hosted in Chromium by e2e/pdfjs/viewer.html
// firefox: Firefox's built-in viewer (pdf.js); same engine as `pdfjs`
module.exports = {
  pdfium: {
    exactPixels: true,     // pages render pixel-for-pixel at 150% zoom
    autoAdvance: false,    // /Dur is ignored; frames are ordinary pages
    scripting: true,       // document JavaScript runs (timers, fields)
    keys: true,            // keystrokes in the capture field reach the game
    buttons: true,         // press-and-hold on push buttons reaches the game
    sleepsOffPage: true,   // a game only runs while its page is current
    links: true,           // link annotations jump to their page
  },
  pdfjs: {
    exactPixels: true,
    autoAdvance: false,
    scripting: true,
    keys: true,
    buttons: true,
    sleepsOffPage: true,
    links: true,
  },
};
module.exports.firefox = module.exports.pdfjs;
