// Snake. Palette: 1 wall, 2 body, 3 head, 4 food, 5 text.
// Keys: w a s d to steer, space (or r) to restart.
var Snake = (function () {
  var WALL = 1, BODY = 2, HEAD = 3, FOOD = 4, TEXT = 5;
  var DIRS = { w: [0, -1], a: [-1, 0], s: [0, 1], d: [1, 0] };
  var g = {};

  function occupied(x, y) {
    for (var i = 0; i < g.body.length; i++)
      if (g.body[i][0] === x && g.body[i][1] === y) return true;
    return false;
  }

  function placeFood(px) {
    var x, y;
    do {
      x = px.randint(1, px.W - 2);
      y = px.randint(1, px.H - 2);
    } while (occupied(x, y));
    g.food = [x, y];
  }

  function reset(px) {
    var cx = Math.floor(px.W / 3), cy = Math.floor(px.H / 2);
    g.body = [[cx, cy], [cx - 1, cy], [cx - 2, cy]];
    g.dir = [1, 0];
    g.turns = [];
    g.alive = true;
    g.started = false;
    g.score = 0;
    g.speed = 7;       // cells per second
    g.acc = 0;
    placeFood(px);
  }

  function queueTurn(d) {
    var prev = g.turns.length ? g.turns[g.turns.length - 1] : g.dir;
    if (d[0] === -prev[0] && d[1] === -prev[1]) return;  // no reversing into yourself
    if (d[0] === prev[0] && d[1] === prev[1]) return;
    if (g.turns.length < 3) g.turns.push(d);
  }

  function move(px) {
    if (g.turns.length) g.dir = g.turns.shift();
    var head = g.body[0];
    var nx = head[0] + g.dir[0], ny = head[1] + g.dir[1];
    var tail = g.body[g.body.length - 1];
    var hitsSelf = occupied(nx, ny) && !(nx === tail[0] && ny === tail[1]);
    if (nx <= 0 || ny <= 0 || nx >= px.W - 1 || ny >= px.H - 1 || hitsSelf) {
      g.alive = false;
      g.best = Math.max(g.best || 0, g.score);
      return;
    }
    g.body.unshift([nx, ny]);
    if (nx === g.food[0] && ny === g.food[1]) {
      g.score += 1;
      g.speed = Math.min(18, 7 + g.score * 0.5);
      placeFood(px);
    } else {
      g.body.pop();
    }
  }

  function draw(px) {
    px.clear(0);
    px.rect(0, 0, px.W, 1, WALL);
    px.rect(0, px.H - 1, px.W, 1, WALL);
    px.rect(0, 0, 1, px.H, WALL);
    px.rect(px.W - 1, 0, 1, px.H, WALL);
    px.set(g.food[0], g.food[1], FOOD);
    for (var i = g.body.length - 1; i >= 0; i--)
      px.set(g.body[i][0], g.body[i][1], i === 0 ? HEAD : BODY);
    if (!g.alive) {
      px.textCentered('GAME OVER', Math.floor(px.H / 2) - 6, TEXT);
      px.textCentered('SPACE', Math.floor(px.H / 2) + 2, TEXT);
    } else if (!g.started) {
      px.textCentered('WASD', Math.floor(px.H / 2) - 8, TEXT);
    }
    px.hud('score', 'SCORE ' + g.score);
    px.hud('best', 'BEST ' + (g.best || 0));
  }

  return {
    state: g,
    init: function (px) { reset(px); draw(px); },
    update: function (px, dt) {
      for (var i = 0; i < px.keys.length; i++) {
        var k = px.keys[i];
        if (!g.alive && (k === ' ' || k === 'r')) { reset(px); break; }
        if (DIRS[k] && g.alive) { queueTurn(DIRS[k]); g.started = true; }
      }
      if (g.alive && g.started) {
        g.acc += dt;
        var step = 1 / g.speed;
        while (g.acc >= step && g.alive) { g.acc -= step; move(px); }
      }
      draw(px);
    }
  };
})();
PX.run(Snake);
