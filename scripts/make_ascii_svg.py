"""Turn assets/photo.png into an animated, colored ASCII portrait (miguel-ascii.svg).

usage: python scripts/make_ascii_svg.py [photo.png] [--cols 128] [--out miguel-ascii.svg]

The photo needs a transparent background (or a plain white one, which is
removed automatically). Each character keeps the color of the pixels it
covers, density follows brightness, and rows reveal top to bottom.
Also writes portrait.txt (plain text) for the live terminal.
"""
from __future__ import annotations

import argparse
import colorsys
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image

from svgkit import ROOT, window, GREEN, MUTED, TEXT

W, H = 840, 880
ART_X0, ART_Y0, ART_W, ART_H = 22, 46, 796, 786
RAMP = " .:-=+*#%@"  # sparse -> dense
FLOOR = 1      # every foreground cell gets at least RAMP[FLOOR]
SHARP = 1.6    # line emphasis
GAMMA = 0.72
LOCAL = 0.7     # 0 = global tones only, 1 = fully local contrast
SHIRT_DIM = 0.62
CROP = (300, 352, 1012, 1170)  # x0, y0, x1, y1 in photo pixels (None = auto)


def load_rgba(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    a = np.array(im).astype(np.float32)
    if a[:, :, 3].min() > 250:  # opaque: knock out a white backdrop
        rgb = a[:, :, :3]
        white = (rgb.min(axis=2) > 236)
        from PIL import ImageDraw
        mask = Image.fromarray((white * 255).astype(np.uint8))
        # flood from the borders so eye whites / highlights stay opaque
        filled = mask.copy()
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
    x0, y0 = max(0, x0 - pw), max(0, y0 - ph)
    x1, y1 = min(im.width, x1 + pw), min(im.height, y1 + 2)  # bust ends at the bottom edge
    return im.crop((x0, y0, x1, y1))


def boost(r, g, b, d=1.0):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    v = 0.38 + 0.64 * d  # brightness follows the (sharpened) tone map
    s = min(1.0, s * 0.92)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def build(photo: Path, cols: int, box=CROP):
    im = crop_to_subject(load_rgba(photo), box=box)
    cw = ART_W / cols
    fs = cw / 0.6  # JetBrains Mono advance = 0.6em
    rh = fs * 1.0
    rows = int(round(cols * cw * im.height / im.width / rh))
    if rows * rh > ART_H:  # too tall: shrink to fit height
        rows = int(ART_H / rh)
    arr = np.array(im).astype(np.float32) / 255.0
    a_full = arr[:, :, 3]
    lum_full = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
    # adaptive histogram equalization pulls detail out of dark curls / beard
    from skimage.exposure import equalize_adapthist
    clahe = equalize_adapthist(np.where(a_full > 0.05, lum_full, 0), kernel_size=max(32, im.width // 10), clip_limit=0.018)
    tone_full = (1 - LOCAL) * lum_full + LOCAL * clahe
    # premultiplied box downsample (rgb, alpha, tone)
    pre = np.dstack([arr[:, :, :3] * a_full[..., None], tone_full * a_full, a_full])
    def down(ch):
        return np.array(Image.fromarray(ch.astype(np.float32), "F").resize((cols, rows), Image.BOX))
    alpha = down(pre[:, :, 4])
    safe = np.maximum(alpha, 1e-3)
    rgb = np.dstack([down(pre[:, :, i]) / safe for i in range(3)])
    tone = down(pre[:, :, 3]) / safe
    # unsharp mask: darken lines (eyes, brows, beard, outline), keep skin solid
    from scipy.ndimage import gaussian_filter
    blur = gaussian_filter(tone, 1.2)
    sharp = np.clip(tone + SHARP * (tone - blur), 0, 1)
    lo, hi = np.percentile(sharp[alpha > 0.38], [3, 99.5])
    sharp = np.clip((sharp - lo) / max(hi - lo, 1e-3), 0, 1)
    # keep the face as the focal point: low-saturation areas (shirt) a bit dimmer
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0)
    sharp *= SHIRT_DIM + (1 - SHIRT_DIM) * np.clip(sat / 0.22, 0, 1)

    grid = []
    for y in range(rows):
        row = []
        for x in range(cols):
            if alpha[y, x] < 0.38:
                row.append((" ", None))
                continue
            d = sharp[y, x] ** GAMMA
            idx = max(FLOOR, int(round(d * (len(RAMP) - 1))))
            c = boost(*(rgb[y, x] * 255), d)
            row.append((RAMP[idx], c))
        grid.append(row)
    return grid, cols, rows, cw, fs, rh


def quantize(grid, n=72):
    """Snap colors to a shared palette so the SVG can use short class names."""
    pts = [c for row in grid for ch, c in row if c]
    pal_img = Image.new("RGB", (len(pts), 1))
    pal_img.putdata(pts)
    q = pal_img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: n * 3]
    idxs = list(q.get_flattened_data()) if hasattr(q, "get_flattened_data") else list(q.getdata())
    out, k = [], 0
    for row in grid:
        r2 = []
        for ch, c in row:
            if c:
                r2.append((ch, idxs[k])); k += 1
            else:
                r2.append((ch, None))
        out.append(r2)
    colors = ["#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]) for i in range(n)]
    return out, colors


def render(grid, colors, cols, rows, cw, fs, rh, prompt: str, name: str) -> str:
    art_w = cols * cw
    x0 = ART_X0 + (ART_W - art_w) / 2
    y0 = ART_Y0 + (ART_H - rows * rh) / 2
    css = [f".p{i}{{fill:{c}}}" for i, c in enumerate(colors)]
    css.append(f".a{{font-size:{fs:.2f}px;white-space:pre;opacity:0;animation:rv .55s ease-out forwards}}")
    css.append("@keyframes rv{0%{opacity:0;filter:brightness(2.4)}60%{opacity:1}100%{opacity:1;filter:brightness(1)}}")
    css.append(f".scan{{fill:url(#sg);opacity:0;animation:sc 2.6s ease-in-out .1s 1 forwards}}")
    css.append(f"@keyframes sc{{0%{{opacity:.9;transform:translateY(0)}}90%{{opacity:.6}}100%{{opacity:0;transform:translateY({rows*rh:.0f}px)}}}}")
    css.append(f".pr{{font-size:12px;fill:{MUTED}}} .pg{{fill:{GREEN}}} .pw{{fill:{TEXT};font-weight:700}}")
    css.append(f".cur{{fill:{TEXT};animation:bl 1.05s steps(1) infinite}} @keyframes bl{{50%{{opacity:0}}}}")
    lines = []
    total = 2.3
    for y, row in enumerate(grid):
        if all(ch == " " for ch, _ in row):
            continue
        # trim trailing blanks, keep leading via x offset
        first = next(i for i, (ch, _) in enumerate(row) if ch != " ")
        last = max(i for i, (ch, _) in enumerate(row) if ch != " ")
        spans, cur_c, buf = [], "x", ""
        for ch, c in row[first:last + 1]:
            key = c if ch != " " else cur_c  # spaces join the current run
            if key != cur_c and buf:
                spans.append((cur_c, buf)); buf = ""
            cur_c = key; buf += ch
        if buf:
            spans.append((cur_c, buf))
        inner = "".join(
            f'<tspan class="p{c}">{escape(t)}</tspan>' if c not in (None, "x") else escape(t)
            for c, t in spans
        )
        n = last - first + 1
        delay = 0.15 + total * y / rows
        lines.append(
            f'<text class="a" x="{x0 + first*cw:.2f}" y="{y0 + (y+0.8)*rh:.2f}" '
            f'textLength="{n*cw:.2f}" lengthAdjust="spacing" xml:space="preserve" '
            f'style="animation-delay:{delay:.2f}s">{inner}</text>'
        )
    scan = (f'<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{GREEN}" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="{GREEN}" stop-opacity=".35"/></linearGradient></defs>'
            f'<rect class="scan" x="{ART_X0}" y="{y0-18:.0f}" width="{ART_W}" height="18"/>')
    py = H - 22
    p_user, p_rest = prompt.split(":", 1)
    prompt_svg = (f'<text class="pr" x="24" y="{py}"><tspan class="pg">{escape(p_user)}</tspan>'
                  f':{escape(p_rest)} whoami  <tspan class="pw">{escape(name)}</tspan></text>'
                  f'<rect class="cur" x="{24 + 7.2*(len(prompt)+len(name)+9):.0f}" y="{py-11}" width="7.5" height="14"/>')
    chars = "".join(ch for row in grid for ch, _ in row) + prompt + name + " whoami"
    body = scan + "\n" + "\n".join(lines) + "\n" + prompt_svg
    return window(W, H, f"{prompt.split(':')[0]}: ~$ ./portrait.sh", body, style="".join(css),
                  chars=chars, desc=f"{name} — ASCII portrait")


def to_text(grid) -> str:
    return "\n".join("".join(ch for ch, _ in row).rstrip() for row in grid).strip("\n") + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", nargs="?", default=str(ROOT / "assets" / "photo.png"))
    ap.add_argument("--cols", type=int, default=136)
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1 or 'auto'")
    ap.add_argument("--out", default=str(ROOT / "miguel-ascii.svg"))
    ap.add_argument("--prompt", default="miguel@creativezone:~$")
    ap.add_argument("--name", default="Miguel")
    args = ap.parse_args()
    box = CROP if args.crop is None else (None if args.crop == "auto" else tuple(int(v) for v in args.crop.split(",")))
    grid, cols, rows, cw, fs, rh = build(Path(args.photo), args.cols, box)
    q, colors = quantize(grid)
    svg = render(q, colors, cols, rows, cw, fs, rh, args.prompt, args.name)
    Path(args.out).write_text(svg, encoding="utf-8")
    # smaller plain-text version for the live terminal's `portrait` command
    g2, *_ = build(Path(args.photo), 76, box)
    (ROOT / "portrait.txt").write_text(to_text(g2), encoding="utf-8")
    print(f"wrote {args.out}: {cols}x{rows} chars, {len(svg)//1024} KB")


if __name__ == "__main__":
    main()
