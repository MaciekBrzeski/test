// pixelpdf interactive runtime.
//
// Runs inside the PDF viewer's JavaScript engine (PDFium in Chrome/Edge,
// Acrobat/Reader). Written in ES5 on purpose: Acrobat's engine is old.
//
// The display is a grid of cells. Each grid row is backed by one comb
// text field per palette colour; a cell of colour k is a glyph (e.g. a
// ZapfDingbats square) in row field k, and a space in the others. Colour 0
// draws nothing, letting the page's static artwork show through. Only
// fields whose text changed are written on each frame.
//
// A game is an object with optional init(px) and update(px, dt)
// functions, registered with px.run(game).
//
// PXRuntime(cfg) creates one independent instance per game page and
// registers it as PXR[cfg.id]; field names are prefixed with the id, so
// several games can live in one document. An instance only runs while its
// page (cfg.page) is the viewer's current page.

var PXR = {};
var PX_DOC = this;

function PXRuntime(cfg) {
  var W = cfg.cols, H = cfg.rows, K = cfg.colors;
  var px = {
    W: W, H: H, colors: K, frame: 0, time: 0, paused: false,
    keys: [], version: '1'
  };

  // -- framebuffer -----------------------------------------------------------
  var buf = [], rowFields = [], shown = [], dirty = [], blank = [];
  var r, k, i;
  for (i = 0; i < W * H; i++) buf.push(0);
  for (i = 0; i < W; i++) blank.push(' ');
  for (r = 0; r < H; r++) {
    rowFields.push([]);
    shown.push([]);
    dirty.push(true);
    for (k = 1; k < K; k++) {
      rowFields[r].push(getField(cfg.prefix + r + '_' + k));
      shown[r].push(null);
    }
  }

  px.clear = function (c) {
    c = c || 0;
    for (var j = 0; j < W * H; j++) buf[j] = c;
    for (var y = 0; y < H; y++) dirty[y] = true;
  };
  px.set = function (x, y, c) {
    x = Math.floor(x); y = Math.floor(y);
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    var j = y * W + x;
    if (buf[j] !== c) { buf[j] = c; dirty[y] = true; }
  };
  px.get = function (x, y) {
    x = Math.floor(x); y = Math.floor(y);
    if (x < 0 || y < 0 || x >= W || y >= H) return -1;
    return buf[y * W + x];
  };
  px.rect = function (x, y, w, h, c) {
    for (var yy = y; yy < y + h; yy++)
      for (var xx = x; xx < x + w; xx++) px.set(xx, yy, c);
  };
  px.line = function (x0, y0, x1, y1, c) {
    x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
    var dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
    var sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx + dy;
    for (;;) {
      px.set(x0, y0, c);
      if (x0 === x1 && y0 === y1) break;
      var e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  };

  // 3x5 font: 15 bits per glyph, rows top to bottom.
  var FONT = {
    '0': '111101101101111', '1': '010110010010111', '2': '111001111100111',
    '3': '111001111001111', '4': '101101111001001', '5': '111100111001111',
    '6': '111100111101111', '7': '111001010010010', '8': '111101111101111',
    '9': '111101111001111', 'A': '010101111101101', 'B': '110101110101110',
    'C': '011100100100011', 'D': '110101101101110', 'E': '111100110100111',
    'F': '111100110100100', 'G': '011100101101011', 'H': '101101111101101',
    'I': '111010010010111', 'J': '001001001101010', 'K': '101101110101101',
    'L': '100100100100111', 'M': '101111111101101', 'N': '110101101101101',
    'O': '010101101101010', 'P': '110101110100100', 'Q': '010101101110011',
    'R': '110101110101101', 'S': '011100010001110', 'T': '111010010010010',
    'U': '101101101101111', 'V': '101101101101010', 'W': '101101111111101',
    'X': '101101010101101', 'Y': '101101010010010', 'Z': '111001010100111',
    ' ': '000000000000000', '!': '010010010000010', ':': '000010000010000',
    '-': '000000111000000', '.': '000000000000010', '?': '111001010000010'
  };
  px.textWidth = function (s) { return s.length ? s.length * 4 - 1 : 0; };
  px.text = function (s, x, y, c) {
    s = String(s).toUpperCase();
    for (var n = 0; n < s.length; n++) {
      var bits = FONT[s.charAt(n)] || FONT['?'];
      for (var b = 0; b < 15; b++)
        if (bits.charAt(b) === '1') px.set(x + n * 4 + (b % 3), y + Math.floor(b / 3), c);
    }
  };
  px.textCentered = function (s, y, c) {
    px.text(s, Math.floor((W - px.textWidth(String(s))) / 2), y, c);
  };

  // PDFium/Acrobat draw field text with the field's own font (ZapfDingbats);
  // pdf.js (Firefox) draws it with web fonts, so it needs a Unicode glyph.
  var glyph = cfg.glyph;
  if (typeof app !== 'undefined' && app && app.viewerType === 'PDF.js' && cfg.unicodeGlyph)
    glyph = cfg.unicodeGlyph;
  px.glyph = glyph;

  function flush() {
    for (var y = 0; y < H; y++) {
      if (!dirty[y]) continue;
      dirty[y] = false;
      var rows = [];
      for (var kk = 1; kk < K; kk++) rows.push(null);
      var base = y * W;
      for (var x = 0; x < W; x++) {
        var c = buf[base + x];
        if (c > 0 && c < K) {
          if (!rows[c - 1]) rows[c - 1] = blank.slice();
          rows[c - 1][x] = glyph;
        }
      }
      for (var k2 = 0; k2 < K - 1; k2++) {
        var s = rows[k2] ? rows[k2].join('') : '';
        if (shown[y][k2] !== s) {
          shown[y][k2] = s;
          rowFields[y][k2].value = s;
        }
      }
    }
  }
  px._flush = flush;

  // -- text fields outside the grid ------------------------------------------
  var hudCache = {};
  px.hud = function (name, value) {
    value = String(value);
    if (hudCache[name] === value) return;
    hudCache[name] = value;
    var f = getField(cfg.id + '_hud_' + name);
    if (f) f.value = value;
  };

  // -- input -----------------------------------------------------------------
  // Keyboard: keystrokes typed into the capture field (no key-up events, so
  // a key counts as held for holdMs after its last repeat). Buttons: real
  // press and release events.
  var pending = [], heldUntil = {}, down = {};
  function now() { return new Date().getTime(); }
  px._key = function (ch) {
    if (!ch) return;
    ch = String(ch).toLowerCase();
    for (var n = 0; n < ch.length; n++) {
      var c = ch.charAt(n);
      pending.push(c);
      heldUntil[c] = now() + cfg.holdMs;
      if (c === cfg.pauseKey) px.paused = !px.paused;
    }
  };
  px._down = function (ch) { down[ch] = true; px._key(ch); };
  px._up = function (ch) { down[ch] = false; };
  px.pressed = function (ch) {
    for (var n = 0; n < px.keys.length; n++) if (px.keys[n] === ch) return true;
    return false;
  };
  px.held = function (ch) { return !!down[ch] || now() < (heldUntil[ch] || 0); };

  // -- randomness ------------------------------------------------------------
  // Park-Miller "minimal standard" generator: exact in double arithmetic,
  // so it runs identically in every engine, ES5 ones included.
  var seed = (Math.abs(Math.floor(cfg.seed)) % 2147483646) + 1;
  px.random = function () {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  px.randint = function (lo, hi) { return lo + Math.floor(px.random() * (hi - lo + 1)); };
  for (i = 0; i < 8; i++) px.random();  // small seeds give small first outputs

  // -- main loop -------------------------------------------------------------
  var game = null, last = 0, timer = null, keyField = null;

  px.step = function (dt) {  // one frame; also used by tests
    px.keys = pending;
    pending = [];
    if (!px.paused) {
      px.time += dt;
      px.frame += 1;
      if (game && game.update) game.update(px, dt);
    }
    flush();
  };

  px.active = function () {
    return cfg.page === null || cfg.page === undefined || !PX_DOC ||
      typeof PX_DOC.pageNum !== 'number' || PX_DOC.pageNum === cfg.page;
  };

  px._tick = function () {
    var t = now();
    var dt = Math.min((t - last) / 1000, 0.1);
    last = t;
    if (!px.active()) return;  // another page is in view: sleep
    if (keyField && keyField.value !== '') keyField.value = '';
    try {
      px.step(dt);
    } catch (e) {
      px.hud('error', 'error: ' + e);
    }
  };

  px.run = function (g) {
    game = g;
    if (game.init) game.init(px);
    flush();
  };

  px.start = function () {
    if (cfg.keyField) keyField = getField(cfg.keyField);
    last = now();
    timer = app.setInterval('PXR["' + cfg.id + '"]._tick()', Math.max(10, Math.round(1000 / cfg.fps)));
  };

  PXR[cfg.id] = px;
  return px;
}
