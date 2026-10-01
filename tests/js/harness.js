// Runs the pixelpdf runtime and a game outside the PDF viewer, with fake
// form fields, for tests.
//
//   node harness.js <scenario.json>
//
// scenario: {runtime, game, config, setup, steps: [{keys, down, up, frames, dt, eval}]}
// The runtime is instantiated as the global PX, and the game source runs
// at top level, so tests can reach its state (e.g. Snake.state).
// Prints JSON: {grid, hud, writes, frame, paused, results}.
'use strict';
const fs = require('fs');
const vm = require('vm');

const scenario = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const fields = {};
let writes = 0;
function makeField(name) {
  let value = '';
  return {
    name,
    get value() { return value; },
    set value(v) { value = String(v); writes += 1; },
  };
}
global.getField = (name) => fields[name] || (fields[name] = makeField(name));
// Timers are recorded, not run: tests drive frames with PX.step / PX._tick.
global.app = { intervals: [], setInterval: (expr, ms) => { app.intervals.push([expr, ms]); return 1; },
               clearInterval: () => {} };
if (scenario.viewerType) global.app.viewerType = scenario.viewerType;

vm.runInThisContext('var PX_CONFIG = ' + JSON.stringify(scenario.config) + ';');
// Filenames let V8 coverage (c8) attribute executed lines to the real files.
vm.runInThisContext(fs.readFileSync(scenario.runtime, 'utf8'), { filename: scenario.runtime });
vm.runInThisContext('var PX = PXRuntime(PX_CONFIG);');
if (scenario.game) vm.runInThisContext(fs.readFileSync(scenario.game, 'utf8'), { filename: scenario.game });
if (scenario.setup) vm.runInThisContext(scenario.setup);

const results = [];
for (const step of scenario.steps || []) {
  if (step.keys) PX._key(step.keys);
  if (step.down) PX._down(step.down);
  if (step.up) PX._up(step.up);
  for (let i = 0; i < (step.frames || 0); i++) PX.step(step.dt || 1 / 30);
  if (step.eval) results.push(vm.runInThisContext(step.eval));
}

const cfg = scenario.config;
const grid = [];
for (let y = 0; y < cfg.rows; y++) {
  let row = '';
  for (let x = 0; x < cfg.cols; x++) row += PX.get(x, y).toString(36);
  grid.push(row);
}
const hud = {};
const hudPrefix = cfg.id + '_hud_';
for (const name of Object.keys(fields)) if (name.startsWith(hudPrefix)) hud[name.slice(hudPrefix.length)] = fields[name].value;
const rowFields = {};
for (const name of Object.keys(fields)) if (name.startsWith(cfg.prefix)) rowFields[name] = fields[name].value;
console.log(JSON.stringify({ grid, hud, writes, rowFields, frame: PX.frame, paused: PX.paused, results }));
