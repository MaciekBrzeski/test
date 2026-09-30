// Breakout. Palette: 1 wall, 2 paddle, 3 ball, 4-8 bricks (by row), 9 text.
// Keys: a / d move the paddle, space launches the ball (and restarts).
var Breakout = (function () {
  var WALL = 1, PADDLE = 2, BALL = 3, BRICK0 = 4, BRICK_COLORS = 5, TEXT = 9;
  var BRICK_W = 4, TOP = 4;
  var g = {};

  function buildBricks(px) {
    g.bricks = [];
    var cols = Math.floor((px.W - 2) / BRICK_W);
    g.brickX0 = 1 + Math.floor(((px.W - 2) - cols * BRICK_W) / 2);
    for (var r = 0; r < BRICK_COLORS * 2; r++) {
      var row = [];
      for (var c = 0; c < cols; c++) row.push(1);
      g.bricks.push(row);
    }
    g.left = cols * BRICK_COLORS * 2;
  }

  function reset(px, keepLevel) {
    if (!keepLevel) { g.level = 1; g.score = 0; g.lives = 3; }
    g.pw = 8;
    g.paddle = Math.floor((px.W - g.pw) / 2);
    g.state = 'serve';
    buildBricks(px);
    serve(px);
  }

  function serve(px) {
    g.state = 'serve';
    g.bx = g.paddle + g.pw / 2;
    g.by = px.H - 4;
    var speed = 16 + 3 * g.level;
    g.vx = speed * 0.55;
    g.vy = -speed * 0.83;
  }

  // Brick cell under (x, y), or null.
  function brickAt(x, y) {
    var r = Math.floor(y) - TOP;
    if (r < 0 || r >= g.bricks.length) return null;
    var c = Math.floor((Math.floor(x) - g.brickX0) / BRICK_W);
    if (c < 0 || c >= g.bricks[r].length || !g.bricks[r][c]) return null;
    if ((Math.floor(x) - g.brickX0) % BRICK_W === BRICK_W - 1) return null;  // gap column
    return [r, c];
  }

  function hitBrick(b) {
    g.bricks[b[0]][b[1]] = 0;
    g.left -= 1;
    g.score += 10 * (BRICK_COLORS * 2 - b[0]);
  }

  function stepBall(px, dt) {
    var steps = Math.ceil(Math.max(Math.abs(g.vx), Math.abs(g.vy)) * dt / 0.4);
    var h = dt / steps;
    for (var s = 0; s < steps; s++) {
      var nx = g.bx + g.vx * h, ny = g.by + g.vy * h;
      // Walls.
      if (nx < 1) { nx = 2 - nx; g.vx = Math.abs(g.vx); }
      if (nx >= px.W - 1) { nx = 2 * (px.W - 1) - nx - 0.001; g.vx = -Math.abs(g.vx); }
      if (ny < 1) { ny = 2 - ny; g.vy = Math.abs(g.vy); }
      // Bricks: test each axis separately to know which way to bounce.
      var bx = brickAt(nx, g.by), by = brickAt(g.bx, ny);
      if (bx) { hitBrick(bx); g.vx = -g.vx; nx = g.bx; }
      if (by) { hitBrick(by); g.vy = -g.vy; ny = g.by; }
      if (!bx && !by) {
        var bd = brickAt(nx, ny);
        if (bd) { hitBrick(bd); g.vx = -g.vx; g.vy = -g.vy; nx = g.bx; ny = g.by; }
      }
      // Paddle: bounce angle depends on where the ball lands.
      var py = px.H - 3;
      if (g.vy > 0 && g.by < py && ny >= py && nx >= g.paddle - 0.5 && nx < g.paddle + g.pw + 0.5) {
        var t = (nx - g.paddle) / g.pw - 0.5;          // -0.5 .. 0.5
        var speed = Math.sqrt(g.vx * g.vx + g.vy * g.vy);
        var angle = t * 2.2;                           // up to ~63 degrees
        g.vx = speed * Math.sin(angle);
        g.vy = -speed * Math.cos(angle);
        ny = py - 0.01;
      }
      g.bx = nx; g.by = ny;
      if (g.by >= px.H) {
        g.lives -= 1;
        if (g.lives <= 0) { g.state = 'over'; } else { serve(px); }
        return;
      }
      if (g.left === 0) {
        g.level += 1;
        g.lives = Math.min(g.lives + 1, 5);
        buildBricks(px);
        serve(px);
        return;
      }
    }
  }

  function draw(px) {
    px.clear(0);
    px.rect(0, 0, px.W, 1, WALL);
    px.rect(0, 0, 1, px.H, WALL);
    px.rect(px.W - 1, 0, 1, px.H, WALL);
    for (var r = 0; r < g.bricks.length; r++)
      for (var c = 0; c < g.bricks[r].length; c++)
        if (g.bricks[r][c]) px.rect(g.brickX0 + c * BRICK_W, TOP + r, BRICK_W - 1, 1, BRICK0 + Math.floor(r / 2));
    px.rect(Math.round(g.paddle), px.H - 3, g.pw, 1, PADDLE);
    if (g.state !== 'over') px.set(g.bx, g.by, BALL);
    if (g.state === 'serve') px.textCentered('SPACE', px.H - 12, TEXT);
    if (g.state === 'over') {
      px.textCentered('GAME OVER', px.H - 16, TEXT);
      px.textCentered('SPACE', px.H - 10, TEXT);
    }
    px.hud('score', 'SCORE ' + g.score);
    px.hud('lives', 'LIVES ' + g.lives + '  LEVEL ' + g.level);
  }

  return {
    state: g,
    init: function (px) { reset(px, false); draw(px); },
    update: function (px, dt) {
      var move = 0;
      for (var i = 0; i < px.keys.length; i++) {
        var k = px.keys[i];
        if (k === 'a') move -= 2;
        if (k === 'd') move += 2;
        if (k === ' ') {
          if (g.state === 'serve') g.state = 'play';
          else if (g.state === 'over') { reset(px, false); }
        }
      }
      // Buttons report real holds: glide while pressed.
      if (px.held('a')) move -= 30 * dt;
      if (px.held('d')) move += 30 * dt;
      g.paddle = Math.max(1, Math.min(px.W - 1 - g.pw, g.paddle + move));
      if (g.state === 'serve') { g.bx = g.paddle + g.pw / 2; g.by = px.H - 4; }
      if (g.state === 'play') stepBall(px, dt);
      draw(px);
    }
  };
})();
PX.run(Breakout);
