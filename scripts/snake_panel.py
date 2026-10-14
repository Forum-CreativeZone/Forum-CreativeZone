"""Wrap Platane/snk's output (dist/snake-raw.svg) in the same dark terminal window as the other cards.

usage: python scripts/snake_panel.py   ->  dist/snake.svg
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svgkit import ROOT, window  # noqa: E402

PROMPT = "miguel@creativezone"


def main():
    raw_p = ROOT / "dist" / "snake-raw.svg"
    if not raw_p.exists():
        print("dist/snake-raw.svg not found, skipping")
        return
    raw = raw_p.read_text(encoding="utf-8")
    m = re.search(r'viewBox="([-\d.]+)[ ,]+([-\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)"', raw)
    vx, vy, vw, vh = (float(v) for v in m.groups())
    W, pad, top = 860, 20, 44
    iw = W - 2 * pad
    ih = iw * vh / vw
    H = int(top + ih + 18)
    inner = re.sub(r"^.*?<svg\b[^>]*>", "", raw, count=1, flags=re.S)
    inner = re.sub(r"</svg>\s*$", "", inner)
    nested = (f'<svg x="{pad}" y="{top}" width="{iw}" height="{ih:.1f}" viewBox="{vx} {vy} {vw} {vh}">'
              f"{inner}</svg>")
    out = window(W, H, f"{PROMPT}: ~$ ./snake.sh", nested, desc="Cobrinha comendo o gráfico de contribuições")
    (ROOT / "dist" / "snake.svg").write_text(out, encoding="utf-8")
    raw_p.unlink()
    print(f"dist/snake.svg {W}x{H}")


if __name__ == "__main__":
    main()
