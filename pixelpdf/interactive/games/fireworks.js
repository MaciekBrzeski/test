// Fireworks: a particle-physics toy.
// Palette: 1 ground, 2-6 spark colours from hot to cooling, 7 rocket, 8 text.
// Keys: space launches a rocket, a / d push the wind, s toggles gravity.
var Fireworks = (function () {
  var GROUND = 1, HOT = 2, SHADES = 5, ROCKET = 7, TEXT = 8;
  var MAX = 500;
  var g = { parts: [], rockets: [], wind: 0, gravity: true, next: 0 };

  function launch(px) {
    g.rockets.push({
      x: px.randint(8, px.W - 9), y: px.H - 3,
      vx: (px.random() - 0.5) * 8, vy: -(30 + px.random() * 10)
    });
  }

  function explode(px, r) {
    var n = 40 + px.randint(0, 40);
    var speed = 8 + px.random() * 10;
    var shift = px.randint(0, 1);  // some bursts start one shade cooler
    for (var i = 0; i < n && g.parts.length < MAX; i++) {
      var a = px.random() * Math.PI * 2, s = speed * (0.3 + 0.7 * px.random());
      g.parts.push({ x: r.x, y: r.y, vx: Math.cos(a) * s + r.vx * 0.3, vy: Math.sin(a) * s + r.vy * 0.1,
                     age: 0, life: 1.2 + px.random() * 1.6, shift: shift });
    }
  }

  function physics(px, dt) {
    var grav = g.gravity ? 22 : 0, ground = px.H - 2;
    for (var i = g.rockets.length - 1; i >= 0; i--) {
      var r = g.rockets[i];
      r.vy += grav * dt;
      r.vx += g.wind * dt;
      r.x += r.vx * dt;
      r.y += r.vy * dt;
      if (r.vy > -4 || r.y < 3) { explode(px, r); g.rockets.splice(i, 1); }
    }
    var drag = Math.exp(-0.9 * dt);
    for (var j = g.parts.length - 1; j >= 0; j--) {
      var p = g.parts[j];
      p.vx = (p.vx + g.wind * dt) * drag;
      p.vy = (p.vy + grav * dt) * drag;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (p.y >= ground) { p.y = ground - (p.y - ground); p.vy = -Math.abs(p.vy) * 0.45; p.vx *= 0.8; }
      if (p.x < 0 || p.x >= px.W) { p.vx = -p.vx * 0.6; p.x = Math.max(0, Math.min(px.W - 0.01, p.x)); }
      p.age += dt;
      if (p.age >= p.life) g.parts.splice(j, 1);
    }
  }

  function draw(px) {
    px.clear(0);
    px.rect(0, px.H - 1, px.W, 1, GROUND);
    for (var j = 0; j < g.parts.length; j++) {
      var p = g.parts[j];
      var shade = Math.min(SHADES - 1, Math.floor(p.age / p.life * SHADES) + p.shift);
      px.set(p.x, p.y, HOT + shade);
    }
    for (var i = 0; i < g.rockets.length; i++) {
      px.set(g.rockets[i].x, g.rockets[i].y, ROCKET);
      px.set(g.rockets[i].x, g.rockets[i].y + 1, HOT + SHADES - 1);
    }
    if (px.time < 4) px.textCentered('SPACE', 4, TEXT);
    px.hud('count', 'SPARKS ' + g.parts.length);
    px.hud('wind', 'WIND ' + (g.wind > 0 ? '+' : '') + g.wind + (g.gravity ? '' : '  ZERO-G'));
  }

  return {
    state: g,
    init: function (px) { g.next = 0.5; draw(px); },
    update: function (px, dt) {
      for (var i = 0; i < px.keys.length; i++) {
        var k = px.keys[i];
        if (k === ' ') launch(px);
        if (k === 'a') g.wind = Math.max(-12, g.wind - 3);
        if (k === 'd') g.wind = Math.min(12, g.wind + 3);
        if (k === 's') g.gravity = !g.gravity;
      }
      g.next -= dt;
      if (g.next <= 0) { launch(px); g.next = 0.6 + px.random() * 1.4; }
      physics(px, dt);
      draw(px);
    }
  };
})();
PX.run(Fireworks);
