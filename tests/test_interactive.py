import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pixelpdf.interactive import RUNTIME_JS, InteractiveDocument
from pixelpdf.interactive.games import GAMES, build_game, game_source

pikepdf = pytest.importorskip("pikepdf")

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "pixelpdf" / "interactive" / "runtime.js"
GAME_DIR = ROOT / "pixelpdf" / "interactive" / "games"
HARNESS = Path(__file__).resolve().parent / "js" / "harness.js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def tiny_doc(**display):
    doc = InteractiveDocument(dpi=72, fps=20)
    page = doc.new_page(background=0, size=(200, 200))
    page.display(10, 10, display.get("cols", 8), display.get("rows", 4), 10,
                 display.get("palette", [None, "#ff0000", "#00ff00"]))
    page.hud("score", 10, 150, 100, 20)
    page.key_capture(10, 175, 60, 20)
    page.button("a", 100, 175, 40, 20, label="<")
    page.set_game("PX.run({});")
    return doc


# -- PDF structure -----------------------------------------------------------

def test_fields_and_flags():
    doc = tiny_doc()
    with pikepdf.open(io.BytesIO(doc.to_bytes())) as pdf:
        assert pdf.check_pdf_syntax() == []
        fields = {str(f.T): f for f in pdf.Root.AcroForm.Fields}
        rows = [n for n in fields if n.startswith("g0_px")]
        assert len(rows) == 4 * 2  # rows x (colours - 1)
        row = fields["g0_px0_1"]
        flags = int(row.Ff)
        assert flags & 1                      # read-only: no highlight, no editing
        assert flags & (1 << 24)              # comb: one glyph per cell
        assert int(row.MaxLen) == 8
        assert "/ZaDb" in str(row.DA) and "1 0 0 rg" in str(row.DA)
        assert [float(v) for v in fields["g0_px0_1"].Rect] == [10, 180, 90, 190]
        assert [float(v) for v in fields["g0_px3_2"].Rect] == [10, 150, 90, 160]
        assert int(fields["g0_hud_score"].Ff) & 1
        keys = fields["g0_keys"]
        assert not int(keys.Ff) & 1           # the capture field must be editable
        assert 'PXR["g0"]._key' in str(keys.AA.K.JS)
        btn = fields["g0_btn_0"]
        assert int(btn.Ff) & (1 << 16)        # push button
        assert 'PXR["g0"]._down("a")' in str(btn.AA.D.JS)
        assert 'PXR["g0"]._up("a")' in str(btn.AA.U.JS)
        assert set(pdf.Root.AcroForm.DR.Font.keys()) == {"/Cour", "/Helv", "/ZaDb"}
        js = str(pdf.Root.OpenAction.JS)
        assert js.count("function PXRuntime(") == 1
        assert 'PXRuntime({"id": "g0", "page": 0' in js and "PX.start();" in js


def instance_configs(script: str) -> list[dict]:
    configs = []
    for chunk in script.split("var PX = PXRuntime(")[1:]:
        configs.append(json.loads(chunk.split(");\n", 1)[0]))
    return configs


def test_config_matches_display():
    doc = tiny_doc(cols=5, rows=3, palette=[None, "#fff", "#000", "#f00"])
    (config,) = instance_configs(doc.script())
    assert config["cols"] == 5 and config["rows"] == 3 and config["colors"] == 4
    assert config["glyph"] == "n" and config["keyField"] == "g0_keys"
    assert config["id"] == "g0" and config["page"] == 0


def test_several_games_in_one_document():
    doc = InteractiveDocument(dpi=72)
    doc.new_page(background=0, size=(100, 100))             # a plain page first
    for game in ("snake", "fireworks"):
        page = doc.new_page(background=0, size=(200, 200))
        page.display(10, 10, 8, 4, 10, [None, "#ff0000"])
        page.key_capture(10, 175, 60, 20)
        page.set_game(f"PX.run({{}}); // {game}")
    script = doc.script()
    assert script.count("function PXRuntime(") == 1
    assert [(c["id"], c["page"]) for c in instance_configs(script)] == [("g0", 1), ("g1", 2)]
    with pikepdf.open(io.BytesIO(doc.to_bytes())) as pdf:
        names = {str(f.T) for f in pdf.Root.AcroForm.Fields}
        assert {"g0_px0_1", "g1_px0_1", "g0_keys", "g1_keys"} <= names
        assert "/Annots" not in pdf.pages[0].obj or len(pdf.pages[0].obj.Annots) == 0


def test_builder_validation():
    doc = InteractiveDocument()
    page = doc.new_page()
    with pytest.raises(ValueError):
        doc.to_bytes()  # no display / game
    with pytest.raises(ValueError):
        page.display(0, 0, 4, 4, 10, [None])  # palette too short
    with pytest.raises(ValueError):
        page.display(0, 0, 4, 4, 10, [None, 0], glyph="star")
    page.display(0, 0, 4, 4, 10, [None, 0])
    with pytest.raises(ValueError):
        page.display(0, 0, 4, 4, 10, [None, 0])  # only one display per page
    with pytest.raises(ValueError):
        doc.to_bytes()                            # display without a game
    with pytest.raises(ValueError):
        page.button("left", 0, 0, 10, 10)


@pytest.mark.parametrize("name", sorted(GAMES))
def test_game_pdfs_are_valid(name):
    with pikepdf.open(io.BytesIO(build_game(name).to_bytes())) as pdf:
        assert pdf.check_pdf_syntax() == []
        assert len(pdf.pages) == 1
        assert "PX.run(" in str(pdf.Root.OpenAction.JS)


@needs_node
@pytest.mark.parametrize("name", sorted(GAMES))
def test_full_script_is_valid_javascript(tmp_path, name):
    path = tmp_path / "script.js"
    path.write_text(build_game(name).script())
    subprocess.run([NODE, "--check", str(path)], check=True)


def test_runtime_is_es5():
    # Acrobat's engine predates ES2015; keep the runtime and games to ES5.
    for source in [RUNTIME_JS] + [game_source(n) for n in GAMES]:
        for token in ("=>", "let ", "const ", "class ", "`", "Math.imul"):
            assert token not in source, token


# -- runtime and games, run in node ------------------------------------------

def run_js(tmp_path, game=None, config=None, steps=(), setup=None, viewer_type=None):
    cfg = {"id": "g0", "page": None, "cols": 10, "rows": 6, "colors": 4, "prefix": "px",
           "glyph": "n", "fps": 30, "seed": 5, "holdMs": 150, "pauseKey": "p", "keyField": None}
    cfg.update(config or {})
    scenario = {"runtime": str(RUNTIME), "config": cfg, "steps": list(steps), "setup": setup,
                "game": str(GAME_DIR / game) if game else None, "viewerType": viewer_type}
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario))
    out = subprocess.run([NODE, str(HARNESS), str(path)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


@needs_node
def test_runtime_draws_into_row_fields(tmp_path):
    setup = "PX.run({init: function (px) { px.set(0, 0, 1); px.set(3, 0, 2); px.rect(1, 2, 3, 1, 3); }});"
    out = run_js(tmp_path, setup=setup)
    assert out["rowFields"]["px0_1"] == "n" + " " * 9
    assert out["rowFields"]["px0_2"] == "   n" + " " * 6
    assert out["rowFields"]["px2_3"] == " nnn" + " " * 6
    assert out["rowFields"]["px1_1"] == ""   # untouched rows stay empty
    assert out["grid"][0] == "1002000000"


@needs_node
def test_runtime_only_writes_changed_fields(tmp_path):
    setup = "PX.run({update: function (px) { px.set(px.frame % 10, 0, 1); }});"
    out = run_js(tmp_path, setup=setup, steps=[{"frames": 5}])
    # The initial flush clears every field once (6 rows x 3 colours = 18 writes),
    # then each frame changes only row 0 colour 1.
    assert out["writes"] == 18 + 5


@needs_node
def test_runtime_text_hud_random_and_bounds(tmp_path):
    setup = ("PX.run({init: function (px) { px.text('7', 0, 0, 1); px.set(-1, 0, 2); px.set(99, 99, 2);"
             " px.hud('score', 'SCORE 3'); }});")
    steps = [{"eval": "var a = []; for (var i = 0; i < 1000; i++) a.push(PX.random());"
                      "[Math.min.apply(null, a) >= 0, Math.max.apply(null, a) < 1, a[0]]"}]
    out = run_js(tmp_path, setup=setup, steps=steps)
    assert out["grid"][:5] == ["1110000000", "0010000000", "0100000000", "0100000000", "0100000000"]
    assert out["hud"]["score"] == "SCORE 3"
    lo_ok, hi_ok, first = out["results"][0]
    assert lo_ok and hi_ok
    assert run_js(tmp_path, setup=setup, steps=steps)["results"][0][2] == first  # seeded


@needs_node
def test_runtime_keys_pause_and_buttons(tmp_path):
    setup = ("var seen = []; PX.run({update: function (px) { seen.push(px.keys.join('')); }});")
    steps = [
        {"keys": "wa", "frames": 1},
        {"frames": 1},
        {"keys": "p", "frames": 3},            # pause: frames stop counting
        {"eval": "PX.frame"},
        {"keys": "p", "frames": 1},
        {"down": "d", "frames": 1, "eval": "PX.held('d')"},
        {"up": "d", "eval": "PX.held('d')"},
        {"eval": "seen.join('|')"},
    ]
    out = run_js(tmp_path, setup=setup, steps=steps)
    frame_while_paused, held_down, held_up, seen = out["results"]
    assert frame_while_paused == 2
    assert held_down is True
    assert held_up is True  # still inside the keyboard hold window after the press
    assert seen.split("|")[:2] == ["wa", ""]


SNAKE = {"cols": 40, "rows": 30, "colors": 6}


@needs_node
def test_snake_moves_eats_and_dies(tmp_path):
    steps = [
        {"eval": "Snake.state.body[0].join(',')"},
        # Put food right in front of the head, then start moving right.
        {"eval": "Snake.state.food = [Snake.state.body[0][0] + 1, Snake.state.body[0][1]]; 0"},
        {"keys": "d", "frames": 5, "dt": 1 / 7},
        {"eval": "[Snake.state.score, Snake.state.body.length, Snake.state.alive]"},
        {"frames": 60, "dt": 1 / 7},            # keeps going right into the wall
        {"eval": "Snake.state.alive"},
        {"keys": " ", "frames": 1},
        {"eval": "[Snake.state.alive, Snake.state.score, Snake.state.body.length]"},
    ]
    out = run_js(tmp_path, "snake.js", SNAKE, steps)
    start, _, after_eat, alive_after_wall, restarted = out["results"]
    assert start == "13,15"
    assert after_eat == [1, 4, True]
    assert alive_after_wall is False
    assert restarted == [True, 0, 3]
    assert out["hud"]["best"] == "BEST 1"


@needs_node
def test_snake_cannot_reverse_into_itself(tmp_path):
    steps = [{"keys": "d", "frames": 1, "dt": 1 / 7}, {"keys": "a", "frames": 3, "dt": 1 / 7},
             {"eval": "[Snake.state.alive, Snake.state.dir.join(',')]"}]
    out = run_js(tmp_path, "snake.js", SNAKE, steps)
    assert out["results"][0] == [True, "1,0"]


BREAKOUT = {"cols": 44, "rows": 36, "colors": 10}


@needs_node
def test_breakout_with_perfect_paddle_clears_bricks(tmp_path):
    # An autopilot keeps the paddle under the ball; the ball must stay in
    # bounds, never be lost, and break bricks.
    autopilot = ("var B = Breakout.state; var orig = Breakout.update;"
                 "var minX = 99, maxX = -1, minY = 99;"
                 "Breakout.update = function (px, dt) { B.paddle = Math.max(1, Math.min(px.W - 1 - B.pw,"
                 " B.bx - B.pw / 2)); orig(px, dt); minX = Math.min(minX, B.bx); maxX = Math.max(maxX, B.bx);"
                 " minY = Math.min(minY, B.by); };")
    steps = [{"eval": autopilot + "B.left"}, {"keys": " ", "frames": 30 * 60},
             {"eval": "[B.left, B.lives, B.score, minX, maxX, minY, B.state]"}]
    out = run_js(tmp_path, "breakout.js", BREAKOUT, steps)
    start_bricks = out["results"][0]
    left, lives, score, min_x, max_x, min_y, state = out["results"][1]
    assert start_bricks == 10 * 10
    assert lives >= 3 and state != "over"
    assert score > 0 and (left < start_bricks or out["hud"]["lives"].endswith("LEVEL 2"))
    assert min_x >= 1 and max_x < 43 and min_y >= 1


@needs_node
def test_breakout_loses_lives_without_a_paddle(tmp_path):
    steps = [{"eval": "Breakout.state.pw = 0; 0"}]
    for _ in range(3):
        steps.append({"keys": " ", "frames": 30 * 8})
    steps.append({"eval": "[Breakout.state.lives, Breakout.state.state]"})
    out = run_js(tmp_path, "breakout.js", BREAKOUT, steps)
    assert out["results"][1] == [0, "over"]


FIREWORKS = {"cols": 64, "rows": 48, "colors": 9}


@needs_node
def test_fireworks_particles_stay_in_bounds(tmp_path):
    check = ("var P = Fireworks.state.parts; var ok = true;"
             "for (var i = 0; i < P.length; i++) { var p = P[i];"
             " if (p.x < 0 || p.x >= 64 || p.y > 46.001) ok = false; }"
             "[P.length, ok, P.length <= 500]")
    steps = [{"keys": "   ", "frames": 30 * 4, "eval": check},
             {"keys": "s", "frames": 30, "eval": "Fireworks.state.gravity"},
             {"keys": "ddd", "frames": 1, "eval": "Fireworks.state.wind"}]
    out = run_js(tmp_path, "fireworks.js", FIREWORKS, steps)
    (count, in_bounds, capped), gravity, wind = out["results"]
    assert count > 20 and in_bounds and capped
    assert gravity is False and wind == 9
    assert out["hud"]["count"].startswith("SPARKS ")


@needs_node
def test_runtime_sleeps_while_its_page_is_not_shown(tmp_path):
    setup = "PX_DOC = {pageNum: 0}; PX.run({update: function (px) { px.set(0, 0, 1); }});"
    steps = [{"eval": "PX._tick(); PX.frame"},
             {"eval": "PX_DOC.pageNum = 3; PX._tick(); PX._tick(); PX.frame"},
             {"eval": "PX_DOC.pageNum = 2; PX._tick(); PX.frame"}]
    out = run_js(tmp_path, config={"page": 2}, setup=setup, steps=steps)
    assert out["results"] == [0, 0, 1]


@needs_node
def test_runtime_line(tmp_path):
    out = run_js(tmp_path, setup="PX.run({init: function (px) { px.line(0, 0, 9, 3, 1); }});")
    lit = [(x, y) for y, row in enumerate(out["grid"]) for x, c in enumerate(row) if c == "1"]
    assert (0, 0) in lit and (9, 3) in lit
    assert len(lit) == 10                       # one pixel per column on an x-major line
    assert all(abs(lit[i + 1][1] - lit[i][1]) <= 1 for i in range(len(lit) - 1))


@needs_node
@pytest.mark.parametrize("viewer, glyph", [(None, "n"), ("pdfium", "n"), ("PDF.js", "\u25a0")])
def test_runtime_picks_glyph_for_viewer(tmp_path, viewer, glyph):
    setup = "PX.run({init: function (px) { px.set(2, 0, 1); }});"
    out = run_js(tmp_path, config={"unicodeGlyph": "\u25a0"}, setup=setup, viewer_type=viewer)
    assert out["rowFields"]["px0_1"] == "  " + glyph + " " * 7


@needs_node
def test_runtime_reports_game_errors_in_a_hud_field(tmp_path):
    setup = "PX.run({update: function () { throw new Error('boom'); }});"
    out = run_js(tmp_path, setup=setup, steps=[{"eval": "PX._tick(); PX.frame"}])
    assert out["hud"]["error"] == "error: Error: boom"
    assert out["results"] == [1]


@needs_node
def test_runtime_start_schedules_its_timer_and_clears_the_key_field(tmp_path):
    steps = [{"eval": "getField('g0_keys').value = 'abc'; PX.start(); PX._tick();"
                      "[getField('g0_keys').value, app.intervals[0][0], app.intervals[0][1]]"}]
    out = run_js(tmp_path, config={"keyField": "g0_keys", "fps": 25}, setup="PX.run({});",
                 steps=steps)
    assert out["results"][0] == ["", 'PXR["g0"]._tick()', 40]


@needs_node
def test_breakout_clearing_the_wall_starts_the_next_level(tmp_path):
    steps = [{"keys": " ", "frames": 2},
             {"eval": "Breakout.state.left = 0; 0"},     # as if the last brick just broke
             {"frames": 2},
             {"eval": "[Breakout.state.level, Breakout.state.lives, Breakout.state.left,"
                      " Breakout.state.state]"}]
    out = run_js(tmp_path, "breakout.js", BREAKOUT, steps)
    assert out["results"][1] == [2, 4, 100, "serve"]
    assert out["hud"]["lives"] == "LIVES 4  LEVEL 2"


def test_button_appearance_centres_and_fits_its_label():
    from pixelpdf.interactive.builder import _label_width
    assert _label_width("LAUNCH", 10) == pytest.approx((611 + 5 * 722) / 100)  # L + AUNCH
    doc = InteractiveDocument(dpi=72)
    page = doc.new_page(background=0, size=(200, 100))
    page.display(0, 0, 2, 2, 10, [None, 0])
    page.button(" ", 10, 10, 40, 30, label="A VERY LONG LABEL")
    page.set_game("PX.run({});")
    with pikepdf.open(io.BytesIO(doc.to_bytes())) as pdf:
        btn = [f for f in pdf.Root.AcroForm.Fields if str(f.T) == "g0_btn_0"][0]
        ap = btn.AP.N
        assert [float(v) for v in ap.BBox] == [0, 0, 40, 30]
        ops = ap.read_bytes().decode()
        size = float(ops.split("/Helv ")[1].split()[0])
        assert _label_width("A VERY LONG LABEL", size) <= 40 * 0.9 + 0.01  # shrunk to fit
        assert "(A VERY LONG LABEL) Tj" in ops
