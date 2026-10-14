"""Turn assets/photo.png into an ASCII portrait engraved by a "laser" (miguel-ascii.svg).

usage: python scripts/make_ascii_svg.py [photo.png] [--cols 136] [--seconds 14]

The photo needs a transparent background (or a plain white one, which is
removed automatically). Characters are white/gray only: density and
brightness follow the (contrast-enhanced) tones of the photo. A laser dot
then engraves the picture row by row, left to right, like a raster laser
engraver, while a progress bar fills at the bottom. Pure SVG + SMIL, so it
plays inside a README <img>.

Also writes portrait.txt (plain text) for the live terminal.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image

from svgkit import ROOT, window, GREEN, MUTED, TEXT, DIM, BORDER

W, H = 840, 880
ART_X0, ART_Y0, ART_W, ART_H = 22, 50, 796, 766
RAMP = " .:-=+*#%@"  # sparse -> dense
FLOOR = 1      # every foreground cell gets at least RAMP[FLOOR]
SHARP = 1.6    # line emphasis
GAMMA = 0.72
LOCAL = 0.7    # 0 = global tones only, 1 = fully local contrast
SHIRT_DIM = 0.62
LEVELS = 9     # gray shades used
CROP = (300, 352, 1012, 1170)  # x0, y0, x1, y1 in photo pixels (None = auto)
START = 0.8    # seconds before the laser starts


def load_rgba(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    a = np.array(im).astype(np.float32)
    if a[:, :, 3].min() > 250:  # opaque: knock out a white backdrop
        rgb = a[:, :, :3]
        white = (rgb.min(axis=2) > 236)
        from PIL import ImageDraw
        mask = Image.fromarray((white * 255).astype(np.uint8))
        filled = mask.copy()  # flood from the borders so eye whites stay opaque
        for xy in [(0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)]:
            if filled.getpixel(xy) == 255:
                ImageDraw.floodfill(filled, xy, 128)
        bg = np.array(filled) == 128
        a[:, :, 3] = np.where(bg, 0, 255)
        im = Image.fromarray(a.astype(np.uint8), "RGBA")
    return im


def crop_to_subject(im: Image.Image, pad=0.035, box=None) -> Image.Image:
    if box:
        return im.crop(box)
    al = np.array(im)[:, :, 3]
    ys, xs = np.where(al > 12)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    pw, ph = int((x1 - x0) * pad), int((y1 - y0) * pad)
    return im.crop((max(0, x0 - pw), max(0, y0 - ph), min(im.width, x1 + pw), min(im.height, y1 + 2)))


def build(photo: Path, cols: int, box=CROP):
    """Return a grid of (char, tone 0..1 | None) plus cell metrics."""
    im = crop_to_subject(load_rgba(photo), box=box)
    cw = ART_W / cols
    fs = cw / 0.6  # JetBrains Mono advance = 0.6em
    rh = fs * 1.0
    rows = int(round(cols * cw * im.height / im.width / rh))
    if rows * rh > ART_H:
        rows = int(ART_H / rh)
    arr = np.array(im).astype(np.float32) / 255.0
    a_full = arr[:, :, 3]
    lum_full = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
    from skimage.exposure import equalize_adapthist  # local contrast for curls / beard
    clahe = equalize_adapthist(np.where(a_full > 0.05, lum_full, 0), kernel_size=max(32, im.width // 10), clip_limit=0.018)
    tone_full = (1 - LOCAL) * lum_full + LOCAL * clahe
    pre = np.dstack([arr[:, :, :3] * a_full[..., None], tone_full * a_full, a_full])

    def down(ch):
        return np.array(Image.fromarray(ch.astype(np.float32), "F").resize((cols, rows), Image.BOX))

    alpha = down(pre[:, :, 4])
    safe = np.maximum(alpha, 1e-3)
    rgb = np.dstack([down(pre[:, :, i]) / safe for i in range(3)])
    tone = down(pre[:, :, 3]) / safe
    from scipy.ndimage import gaussian_filter
    sharp = np.clip(tone + SHARP * (tone - gaussian_filter(tone, 1.2)), 0, 1)
    lo, hi = np.percentile(sharp[alpha > 0.38], [3, 99.5])
    sharp = np.clip((sharp - lo) / max(hi - lo, 1e-3), 0, 1)
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)  # keep the face as focal point
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0)
    sharp *= SHIRT_DIM + (1 - SHIRT_DIM) * np.clip(sat / 0.22, 0, 1)

    grid = []
    for y in range(rows):
        row = []
        for x in range(cols):
            if alpha[y, x] < 0.38:
                row.append((" ", None))
                continue
            d = float(sharp[y, x] ** GAMMA)
            idx = max(FLOOR, int(round(d * (len(RAMP) - 1))))
            row.append((RAMP[idx], d))
        grid.append(row)
    return grid, cols, rows, cw, fs, rh


def gray(level: int) -> str:
    v = 0.34 + 0.66 * level / (LEVELS - 1)
    return "#%02x%02x%02x" % (int(236 * v), int(240 * v), int(246 * v))


def render(grid, cols, rows, cw, fs, rh, prompt: str, name: str, seconds: float) -> str:
    art_w = cols * cw
    x0 = ART_X0 + (ART_W - art_w) / 2
    y0 = ART_Y0 + (ART_H - rows * rh) / 2
    lines = []
    for y, row in enumerate(grid):
        if any(ch != " " for ch, _ in row):
            first = next(i for i, (ch, _) in enumerate(row) if ch != " ")
            last = max(i for i, (ch, _) in enumerate(row) if ch != " ")
            lines.append((y, first, last))
    n = len(lines)
    per = seconds / n

    css = [f".g{i}{{fill:{gray(i)}}}" for i in range(LEVELS)]
    css.append(f".a{{font-size:{fs:.2f}px;white-space:pre}}")
    css.append(".burn{animation:cool 1.6s ease-out both}"
               "@keyframes cool{0%{filter:brightness(2.2) drop-shadow(0 0 2px #fff)}100%{filter:none}}")
    css.append(f".pr{{font-size:12px;fill:{MUTED}}}.pg{{fill:{GREEN}}}.pw{{fill:{TEXT};font-weight:700}}.pd{{fill:{DIM}}}")
    css.append(f".cur{{fill:{TEXT};animation:bl 1.05s steps(1) infinite}}@keyframes bl{{50%{{opacity:0}}}}")

    defs, rows_svg = [], []
    cx_vals, cx_times, cy_vals, cy_times = [], [], [], []
    for i, (y, first, last) in enumerate(lines):
        t0 = START + i * per
        rx = x0 + first * cw
        rw = (last - first + 1) * cw
        ry = y0 + y * rh
        defs.append(
            f'<clipPath id="c{i}"><rect x="{rx:.1f}" y="{ry - 1:.1f}" width="0" height="{rh + 2:.1f}">'
            f'<animate attributeName="width" from="0" to="{rw + 1:.1f}" begin="{t0:.3f}s" dur="{per:.3f}s" fill="freeze"/></rect></clipPath>'
        )
        row = grid[y][first:last + 1]
        spans, cur, buf = [], "x", ""
        for ch, d in row:
            key = cur if ch == " " else min(LEVELS - 1, int(round(d * (LEVELS - 1))))
            if key != cur and buf:
                spans.append((cur, buf)); buf = ""
            cur = key; buf += ch
        if buf:
            spans.append((cur, buf))
        inner = "".join(f'<tspan class="g{c}">{escape(t)}</tspan>' if c != "x" else escape(t) for c, t in spans)
        rows_svg.append(
            f'<g clip-path="url(#c{i})"><text class="a burn" style="animation-delay:{t0:.2f}s" x="{rx:.2f}" y="{ry + 0.8 * rh:.2f}" '
            f'textLength="{rw:.2f}" lengthAdjust="spacing" xml:space="preserve">{inner}</text></g>'
        )
        k0, k1 = (i * per) / seconds, ((i + 1) * per) / seconds
        cx_vals += [rx, rx + rw]; cx_times += [k0, k1]
        cy_vals.append(ry + rh / 2); cy_times.append(k0)
    cx_times[-1] = 1.0
    T = f"{seconds:.2f}s"
    kt = lambda ts: ";".join(f"{t:.5f}" for t in ts)
    vv = lambda vs: ";".join(f"{v:.1f}" for v in vs)
    top = ART_Y0 - 6

    laser = f"""<g opacity="0">
<animate attributeName="opacity" values="1;1;0" keyTimes="0;0.985;1" begin="{START}s" dur="{seconds + 0.4:.2f}s" fill="freeze"/>
<line x1="{cx_vals[0]:.1f}" y1="{top}" x2="{cx_vals[0]:.1f}" y2="{cy_vals[0]:.1f}" stroke="url(#beam)" stroke-width="1.4">
  <animate attributeName="x1" values="{vv(cx_vals)}" keyTimes="{kt(cx_times)}" begin="{START}s" dur="{T}" fill="freeze"/>
  <animate attributeName="x2" values="{vv(cx_vals)}" keyTimes="{kt(cx_times)}" begin="{START}s" dur="{T}" fill="freeze"/>
  <animate attributeName="y2" values="{vv(cy_vals)}" keyTimes="{kt(cy_times)}" calcMode="discrete" begin="{START}s" dur="{T}" fill="freeze"/>
</line>
<rect x="{cx_vals[0] - 7:.1f}" y="{top - 5}" width="14" height="5" rx="1.5" fill="#2d333b" stroke="{BORDER}">
  <animate attributeName="x" values="{vv([v - 7 for v in cx_vals])}" keyTimes="{kt(cx_times)}" begin="{START}s" dur="{T}" fill="freeze"/>
</rect>
<g>
  <circle r="11" fill="url(#glow)"/><circle r="2.3" fill="#ffffff"/>
  <animateTransform attributeName="transform" type="translate" values="{';'.join(f'{x:.1f} {y:.1f}' for x, y in zip(cx_vals, [cy_vals[i // 2] for i in range(len(cx_vals))]))}" keyTimes="{kt(cx_times)}" begin="{START}s" dur="{T}" fill="freeze"/>
</g>
</g>"""
    grads = (f'<radialGradient id="glow"><stop offset="0" stop-color="#ffffff" stop-opacity=".95"/>'
             f'<stop offset=".25" stop-color="{GREEN}" stop-opacity=".55"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></radialGradient>'
             f'<linearGradient id="beam" gradientUnits="userSpaceOnUse" x1="0" y1="{ART_Y0 - 6}" x2="0" y2="{ART_Y0 + ART_H}"><stop offset="0" stop-color="{GREEN}" stop-opacity=".08"/>'
             f'<stop offset="1" stop-color="{GREEN}" stop-opacity=".55"/></linearGradient>')

    # bottom bar: progress while engraving, then the whoami prompt
    py = H - 24
    bar_x, bar_w = 24 + 7.2 * 23 + 14, 300
    end = START + seconds
    p_user, p_rest = prompt.split(":", 1)
    progress = (
        f'<g><animate attributeName="opacity" values="1;0" begin="{end + 0.3:.2f}s" dur=".4s" fill="freeze"/>'
        f'<text class="pr" x="24" y="{py}"><tspan class="pg">$</tspan> ./portrait.sh --laser</text>'
        f'<rect x="{bar_x:.0f}" y="{py - 10}" width="{bar_w}" height="11" rx="2" fill="#161b22" stroke="{BORDER}"/>'
        f'<rect x="{bar_x:.0f}" y="{py - 10}" width="0" height="11" rx="2" fill="{GREEN}" opacity=".85">'
        f'<animate attributeName="width" from="0" to="{bar_w}" begin="{START}s" dur="{T}" fill="freeze"/></rect>'
        f'<text class="pr pd" x="{bar_x + bar_w + 12:.0f}" y="{py}">gravando…'
        f'<set attributeName="visibility" to="hidden" begin="{end:.2f}s"/></text></g>'
    )
    whoami = (
        f'<g opacity="0"><animate attributeName="opacity" values="0;1" begin="{end + 0.6:.2f}s" dur=".5s" fill="freeze"/>'
        f'<text class="pr" x="24" y="{py}"><tspan class="pg">{escape(p_user)}</tspan>:{escape(p_rest)} whoami  '
        f'<tspan class="pw">{escape(name)}</tspan></text>'
        f'<rect class="cur" x="{24 + 7.2 * (len(prompt) + len(name) + 9):.0f}" y="{py - 11}" width="7.5" height="14"/></g>'
    )
    chars = "".join(ch for row in grid for ch, _ in row) + prompt + name + " whoami$./portrait.sh--lasergravando…"
    body = f"<defs>{grads}{''.join(defs)}</defs>\n" + "\n".join(rows_svg) + "\n" + laser + "\n" + progress + whoami
    return window(W, H, f"{p_user}: ~$ ./portrait.sh --laser", body, style="".join(css),
                  chars=chars, desc=f"{name}, retrato em ASCII gravado a laser")


def to_text(grid) -> str:
    return "\n".join("".join(ch for ch, _ in row).rstrip() for row in grid).strip("\n") + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", nargs="?", default=str(ROOT / "assets" / "photo.png"))
    ap.add_argument("--cols", type=int, default=136)
    ap.add_argument("--seconds", type=float, default=14.0, help="duração da gravação a laser")
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1 or 'auto'")
    ap.add_argument("--out", default=str(ROOT / "miguel-ascii.svg"))
    ap.add_argument("--prompt", default="miguel@creativezone:~$")
    ap.add_argument("--name", default="Miguel")
    args = ap.parse_args()
    box = CROP if args.crop is None else (None if args.crop == "auto" else tuple(int(v) for v in args.crop.split(",")))
    grid, cols, rows, cw, fs, rh = build(Path(args.photo), args.cols, box)
    svg = render(grid, cols, rows, cw, fs, rh, args.prompt, args.name, args.seconds)
    Path(args.out).write_text(svg, encoding="utf-8")
    g2, *_ = build(Path(args.photo), 76, box)
    (ROOT / "portrait.txt").write_text(to_text(g2), encoding="utf-8")
    print(f"wrote {args.out}: {cols}x{rows} chars, {len(svg)//1024} KB, laser {args.seconds}s")


if __name__ == "__main__":
    main()
