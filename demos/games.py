"""Milestone 4 demo: playable games inside PDF files.

    python demos/games.py [outdir]

Writes snake.pdf, breakout.pdf and fireworks.pdf. Open them in Chrome,
Edge or Adobe Acrobat/Reader. Click the key box and type to play, or use
the on-screen buttons.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pixelpdf.interactive.games import GAMES, build_game  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    out.mkdir(parents=True, exist_ok=True)
    for name in GAMES:
        path = out / f"{name}.pdf"
        build_game(name).save(path)
        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
