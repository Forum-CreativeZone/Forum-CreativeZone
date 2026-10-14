"""Render the content-driven parts of the profile from content/profile.json.

Writes (repo root):
  header.svg            banner engraved by a scan line + rotating typed roles
  about.svg             "cat sobre.md" card (420x440, sits beside the portrait)
  cards/<slug>.svg      one terminal card per project (420 wide)
  stack.svg             tech stack as a stack.json listing with icons
  community.svg         Creative Zone card
  README.md             the profile page that ties everything together

Only standard library + Pillow (for the community logo). Run:
  python scripts/render_static.py
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svgkit import ROOT, window, BG, PANEL, BORDER, TEXT, MUTED, DIM, GREEN  # noqa: E402

CONTENT = json.loads((ROOT / "content" / "profile.json").read_text(encoding="utf-8"))
BANNER = json.loads((ROOT / "content" / "banner.json").read_text(encoding="utf-8"))
ICONS = ROOT / "assets" / "icons"
SOFT = "#c9d1d9"
CYAN = "#79c0ff"
RED = "#ff4d4d"
P = CONTENT["prompt_user"]


def wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]


def esc(s: str) -> str:
    return escape(s, {'"': "&quot;"})


# ------------------------------------------------------------------ header

def render_header() -> str:
    W, H = 860, 252
    fs = 13
    cw = fs * 0.6
    bw = max(len(l) for l in BANNER) * cw
    bx, by = (W - bw) / 2, 66
    lh = 16.5
    scan_dur, scan_begin = 3.2, 0.5
    banner = "".join(
        f'<text class="bn" x="{bx:.1f}" y="{by + i * lh:.1f}" xml:space="preserve">{esc(l)}</text>' for i, l in enumerate(BANNER)
    )
    bh = len(BANNER) * lh
    scan = (
        f'<clipPath id="bclip"><rect x="{bx - 4:.1f}" y="{by - 14}" width="0" height="{bh + 8:.1f}">'
        f'<animate attributeName="width" from="0" to="{bw + 8:.1f}" begin="{scan_begin}s" dur="{scan_dur}s" fill="freeze"/></rect></clipPath>'
        f'<g clip-path="url(#bclip)">{banner}</g>'
        f'<g opacity="0"><animate attributeName="opacity" values="1;1;0" keyTimes="0;.9;1" begin="{scan_begin}s" dur="{scan_dur + .3}s" fill="freeze"/>'
        f'<rect x="{bx - 4:.1f}" y="{by - 18}" width="2" height="{bh + 14:.1f}" fill="{GREEN}" filter="url(#gl)">'
        f'<animate attributeName="x" from="{bx - 4:.1f}" to="{bx + bw + 4:.1f}" begin="{scan_begin}s" dur="{scan_dur}s" fill="freeze"/></rect></g>'
    )
    sub_y = by + bh + 14
    who = f'{CONTENT["name"]} · {CONTENT["role"]} · {CONTENT["founder_of"]}'
    sub = (f'<text class="sub fade" style="animation-delay:{scan_begin + scan_dur:.1f}s" x="{W/2}" y="{sub_y:.1f}" text-anchor="middle">{esc(who)}</text>')

    # typed roles: one shared timeline, discrete steps
    lines = CONTENT["typing"]
    tfs, tcw = 17, 17 * 0.6
    tx = 64
    ty = H - 34
    type_dt, del_dt, hold, gap = 0.075, 0.03, 2.4, 0.45
    events = []  # (time, line_index, chars)
    t = 0.0
    for i, l in enumerate(lines):
        for k in range(len(l) + 1):
            events.append((t, i, k)); t += type_dt
        t += hold
        for k in range(len(l), -1, -1):
            events.append((t, i, k)); t += del_dt
        t += gap
    cycle = t
    begin = scan_begin + scan_dur + 0.6
    kts = ";".join(f"{e[0] / cycle:.5f}" for e in events)
    texts = []
    for i, l in enumerate(lines):
        vals = ";".join(f"{(e[2] * tcw + (1 if e[2] else 0)) if e[1] == i else 0:.1f}" for e in events)
        texts.append(
            f'<clipPath id="t{i}"><rect x="{tx}" y="{ty - 20}" width="0" height="28">'
            f'<animate attributeName="width" values="{vals}" keyTimes="{kts}" calcMode="discrete" begin="{begin:.2f}s" dur="{cycle:.2f}s" repeatCount="indefinite"/></rect></clipPath>'
            f'<text class="ty" clip-path="url(#t{i})" x="{tx}" y="{ty}">{esc(l)}</text>'
        )
    curx = ";".join(f"{tx + e[2] * tcw + 2:.1f}" for e in events)
    cursor = (f'<rect class="cur" x="{tx + 2}" y="{ty - 15}" width="9" height="19" fill="{GREEN}">'
              f'<animate attributeName="x" values="{curx}" keyTimes="{kts}" calcMode="discrete" begin="{begin:.2f}s" dur="{cycle:.2f}s" repeatCount="indefinite"/></rect>')
    prompt = f'<text class="pp" x="{tx - 26}" y="{ty}">❯</text>'.replace("❯", "&gt;")
    defs = (f'<defs><filter id="gl" x="-200%" y="-20%" width="500%" height="140%"><feGaussianBlur stdDeviation="2.4"/>'
            f'<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    sep = f'<line x1="40" y1="{ty - 32}" x2="{W - 40}" y2="{ty - 32}" stroke="{BORDER}" stroke-dasharray="2 4"/>'
    css = (f".bn{{fill:{GREEN};font-size:{fs}px;font-weight:700;white-space:pre}}"
           f".sub{{fill:{MUTED};font-size:13px}}.ty{{fill:{TEXT};font-size:{tfs}px;font-weight:700}}.pp{{fill:{GREEN};font-size:{tfs}px;font-weight:700}}"
           ".fade{opacity:0;animation:fi 1.2s ease-out forwards}@keyframes fi{to{opacity:1}}"
           ".cur{animation:bl 1.05s steps(1) infinite}@keyframes bl{50%{opacity:0}}")
    body = defs + scan + sub + sep + prompt + "".join(texts) + cursor
    chars = "".join(BANNER) + who + "".join(lines) + ">"
    return window(W, H, f"{P}: ~", body, style=css, chars=chars,
                  desc=f"CREATIVE ZONE. {who}")


# ------------------------------------------------------------------ about

def render_about() -> str:
    W, H = 420, 440
    a = CONTENT["about"]
    x = 24
    parts, chars = [], ""
    y = 66
    seq = 0

    def add(svg: str, height: float):
        nonlocal y, seq
        parts.append(f'<g class="ln" style="animation-delay:{0.5 + seq * 0.32:.2f}s">{svg}</g>')
        seq += 1
        y += height

    add(f'<text class="nm" x="{x}" y="{y}">{esc(CONTENT["name"])}</text>', 24); chars += CONTENT["name"]
    add(f'<text class="rl" x="{x}" y="{y}">{esc(CONTENT["role"])}</text>', 19); chars += CONTENT["role"]
    fo = CONTENT["founder_of"]
    add(f'<text class="fo" x="{x}" y="{y}">{esc(fo)}</text>', 18); chars += fo
    add(f'<line x1="{x}" y1="{y - 4}" x2="{W - x}" y2="{y - 4}" stroke="{BORDER}" stroke-dasharray="2 4"/>', 16)
    for ptxt in a["paragraphs"]:
        ls = wrap(ptxt, 52)
        block = "".join(f'<text class="pg" x="{x}" y="{y + i * 17:.0f}">{esc(l)}</text>' for i, l in enumerate(ls))
        add(block, len(ls) * 17 + 9)
        chars += ptxt
    y += 2
    for k, v in a["facts"]:
        add(f'<text class="fk" x="{x}" y="{y}">› {esc(k)}</text><text class="fv" x="{x + 64}" y="{y}">{esc(v)}</text>', 19)
        chars += k + v + "›"
    py = H - 24
    parts.append(f'<g class="ln" style="animation-delay:{0.5 + seq * 0.32:.2f}s"><text class="pr" x="{x}" y="{py}"><tspan class="pgr">{esc(P)}</tspan>:~$ </text>'
                 f'<rect class="cur" x="{x + 7.2 * (len(P) + 4):.0f}" y="{py - 11}" width="7.5" height="14" fill="{TEXT}"/></g>')
    chars += P + ":~$ "
    css = (f".pr{{fill:{MUTED};font-size:12px}}.pgr{{fill:{GREEN}}}.cur{{animation:bl 1.05s steps(1) infinite}}@keyframes bl{{50%{{opacity:0}}}}"
           f".nm{{fill:{TEXT};font-size:23px;font-weight:700}}.rl{{fill:{GREEN};font-size:13.5px;font-weight:700}}"
           f".fo{{fill:{SOFT};font-size:12.5px}}.pg{{fill:{SOFT};font-size:12px}}"
           f".fk{{fill:{GREEN};font-size:11.5px}}.fv{{fill:{SOFT};font-size:11.5px}}"
           ".ln{opacity:0;animation:in .9s ease-out forwards}@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}")
    return window(W, H, f"{P}: ~$ cat sobre.md", "".join(parts), style=css, chars=chars,
                  desc=f"Sobre {CONTENT['name']}: {CONTENT['role']}, {fo}")


# ------------------------------------------------------------------ project cards

def lock_icon(x, y, c):
    return (f'<g transform="translate({x},{y})" fill="none" stroke="{c}" stroke-width="1.3">'
            f'<rect x="0" y="4.5" width="9" height="6.5" rx="1.3" fill="{c}" fill-opacity=".15"/><path d="M2 4.5V3a2.5 2.5 0 0 1 5 0v1.5"/></g>')


def render_card(pj: dict, H: int) -> str:
    W = 420
    x = 22
    parts, chars = [], ""
    private = pj["visibility"].startswith("priv")
    pill_c = DIM if private else GREEN
    label = pj["visibility"]
    pw = len(label) * 6.6 + (34 if private else 18)
    parts.append(f'<g class="ln" style="animation-delay:.3s"><text class="nm" x="{x}" y="64">{esc(pj["name"])}</text>'
                 f'<rect x="{W - x - pw:.1f}" y="49" width="{pw:.1f}" height="20" rx="10" fill="none" stroke="{pill_c}"/>'
                 + (lock_icon(W - x - pw + 9, 53.5, pill_c) if private else "")
                 + f'<text class="pl" x="{W - x - (9 if True else 0):.1f}" y="63" text-anchor="end" fill="{pill_c}">{esc(label)}</text></g>')
    parts.append(f'<g class="ln" style="animation-delay:.55s"><text class="bd" x="{x}" y="84">{esc(pj["badge"])}</text></g>')
    chars += pj["name"] + label + pj["badge"]
    y = 110
    tl = wrap(pj["tagline"], 49)
    parts.append(f'<g class="ln" style="animation-delay:.8s">' + "".join(
        f'<text class="tg" x="{x}" y="{y + i * 17}">{esc(l)}</text>' for i, l in enumerate(tl)) + "</g>")
    chars += pj["tagline"]
    y += len(tl) * 17 + 10
    for j, h in enumerate(pj["highlights"]):
        hl = wrap(h, 52)
        parts.append(f'<g class="ln" style="animation-delay:{1.1 + j * 0.3:.2f}s"><text class="ar" x="{x}" y="{y}">›</text>' + "".join(
            f'<text class="hl" x="{x + 13}" y="{y + i * 16}">{esc(l)}</text>' for i, l in enumerate(hl)) + "</g>")
        y += len(hl) * 16 + 4
        chars += h + "›"
    # tech chips, bottom aligned
    cy = H - 36
    cx = x
    for k, t in enumerate(pj["tech"]):
        w = len(t) * 6.3 + 16
        if cx + w > W - x:
            break
        parts.append(f'<g class="chip" style="animation-delay:{2.4 + k * 0.15:.2f}s"><rect x="{cx:.1f}" y="{cy}" width="{w:.1f}" height="21" rx="5" fill="#1c2129" stroke="{BORDER}"/>'
                     f'<text class="ch" x="{cx + w / 2:.1f}" y="{cy + 14.5}" text-anchor="middle">{esc(t)}</text></g>')
        cx += w + 6
        chars += t
    css = (f".nm{{fill:{TEXT};font-size:19px;font-weight:700}}.pl{{font-size:11px}}.bd{{fill:{DIM};font-size:11.5px}}"
           f".tg{{fill:{SOFT};font-size:12.5px}}.ar{{fill:{GREEN};font-size:12px;font-weight:700}}.hl{{fill:#b1bac4;font-size:11.5px}}"
           f".ch{{fill:{SOFT};font-size:10.5px}}"
           ".ln{opacity:0;animation:in .9s ease-out forwards}@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}"
           ".chip{opacity:0;animation:pop .6s ease-out forwards}@keyframes pop{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}")
    return window(W, H, f"~/projetos/{pj['slug']}", "".join(parts), style=css, chars=chars,
                  desc=f"{pj['name']}: {pj['tagline']}")


def card_height(pj: dict) -> int:
    y = 110 + len(wrap(pj["tagline"], 49)) * 17 + 10
    for h in pj["highlights"]:
        y += len(wrap(h, 52)) * 16 + 4
    return int(y + 50)


# ------------------------------------------------------------------ stack

GROUP_LABEL = {"frontend": "frontend", "backend": "backend", "infra": "infra", "ia_mobile": "ia+mobile", "ia_mobile_testes": "ia+mobile",
               "ia_mcp": "ia & mcp", "mobile": "mobile", "testes": "testes"}


def icon(slug: str):
    f = ICONS / f"{slug}.svg"
    if not f.exists():
        return None, slug
    s = f.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", s).group(1)
    path = re.search(r'<path d="([^"]+)"', s).group(1)
    return path, title


NAMES = {"nodedotjs": "Node.js", "githubactions": "Actions", "modelcontextprotocol": "MCP", "tailwindcss": "Tailwind",
         "postgresql": "Postgres", "shadcnui": "shadcn/ui", "radixui": "Radix", "javascript": "JavaScript",
         "typescript": "TypeScript", "cloudflare": "Cloudflare", "tanstack": "TanStack"}


def display_name(slug: str) -> str:
    if slug.startswith("text:"):
        return slug[5:]
    return NAMES.get(slug) or icon(slug)[1]


def render_stack() -> str:
    W = 860
    groups = CONTENT["stack"]
    tile_w, tile_h, gap = 68, 64, 8
    key_w = 168
    row_h = tile_h + 14
    H = 66 + len(groups) * row_h + 30
    parts, chars = [], ""
    x0 = 26
    parts.append(f'<text class="br" x="{x0}" y="60">{{</text>')
    k = 0
    for gi, (gname, items) in enumerate(groups):
        gy = 70 + gi * row_h
        label = GROUP_LABEL.get(gname, gname)
        comma = "," if gi < len(groups) - 1 else ""
        parts.append(f'<g class="ln" style="animation-delay:{0.4 + gi * 0.5:.2f}s"><text class="ky" x="{x0 + 18}" y="{gy + tile_h / 2 + 5:.0f}">"{esc(label)}"<tspan class="br">: [</tspan></text>'
                     f'<text class="br" x="{x0 + key_w + len(items) * (tile_w + gap) + 2}" y="{gy + tile_h / 2 + 5:.0f}">]{comma}</text></g>')
        chars += label + '"[]:,'
        for j, it in enumerate(items):
            tx = x0 + key_w + j * (tile_w + gap)
            if it.startswith("text:"):
                path, name = None, it[5:]
            else:
                path, name = icon(it)
                name = NAMES.get(it, name)
            delay = 0.6 + gi * 0.5 + j * 0.12
            k += 1
            if path:
                ic = f'<g transform="translate({tx + tile_w / 2 - 12:.1f},{gy + 10}) scale(1)"><path d="{path}" fill="{SOFT}"/></g>'
            else:
                ic = f'<text class="mono" x="{tx + tile_w / 2:.1f}" y="{gy + 29}" text-anchor="middle">{esc(name[:2])}</text>'
                chars += name[:2]
            short = name if len(name) <= 10 else name[:9] + "…"
            parts.append(f'<g class="tile" style="animation-delay:{delay:.2f}s"><rect x="{tx}" y="{gy}" width="{tile_w}" height="{tile_h}" rx="9" fill="{PANEL}" stroke="{BORDER}"/>'
                         f'{ic}<text class="nmi" x="{tx + tile_w / 2:.1f}" y="{gy + 53}" text-anchor="middle">{esc(short)}</text></g>')
            chars += short
    parts.append(f'<text class="br" x="{x0}" y="{H - 22}">}}</text>')
    css = (f".br{{fill:{MUTED};font-size:14px}}.ky{{fill:{CYAN};font-size:14px}}.nmi{{fill:{MUTED};font-size:10px}}"
           f".mono{{fill:{SOFT};font-size:17px;font-weight:700}}"
           ".ln{opacity:0;animation:in .8s ease-out forwards}@keyframes in{from{opacity:0}to{opacity:1}}"
           ".tile{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .7s cubic-bezier(.2,1.4,.4,1) forwards}"
           "@keyframes pop{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:none}}")
    return window(W, H, f"{P}: ~$ cat stack.json", "".join(parts), style=css, chars=chars + "{}…",
                  desc="Stack: " + ", ".join(f"{GROUP_LABEL.get(g, g)}" for g, _ in groups))


# ------------------------------------------------------------------ community

def logo_data_uri(size=300) -> str:
    from PIL import Image
    src = ROOT / "assets" / "creativezone-logo.png"
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGBA", im.size, (13, 17, 23, 255))
    bg.alpha_composite(im)
    bg = bg.convert("RGB").resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=86, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def render_community() -> str:
    c = CONTENT["community"]
    W = 860
    lx, ly, ls = 28, 54, 172
    tx = lx + ls + 30
    desc = wrap(c["description"], 82)
    H = max(ly + ls + 28, 54 + 30 + 22 + 26 + len(desc) * 18 + 16 + 30 + 34 + 26)
    parts, chars = [], ""
    parts.append(f'<defs><clipPath id="lg"><rect x="{lx}" y="{ly}" width="{ls}" height="{ls}" rx="18"/></clipPath>'
                 f'<filter id="rg" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter></defs>')
    parts.append(f'<g class="lg"><rect x="{lx}" y="{ly}" width="{ls}" height="{ls}" rx="18" fill="{RED}" opacity=".35" filter="url(#rg)">'
                 f'<animate attributeName="opacity" values=".18;.42;.18" dur="4.5s" repeatCount="indefinite"/></rect>'
                 f'<image href="{logo_data_uri()}" x="{lx}" y="{ly}" width="{ls}" height="{ls}" clip-path="url(#lg)"/>'
                 f'<rect x="{lx + .5}" y="{ly + .5}" width="{ls - 1}" height="{ls - 1}" rx="18" fill="none" stroke="{RED}" stroke-opacity=".7"/></g>')
    y = 80
    name1, _, name2 = c["name"].partition(" ")
    parts.append(f'<g class="ln" style="animation-delay:.5s"><text class="t1" x="{tx}" y="{y}">{esc(name1)} <tspan class="t2">{esc(name2)}</tspan></text>'
                 f'<rect x="{W - 28 - 92}" y="{y - 20}" width="92" height="24" rx="12" fill="{RED}" fill-opacity=".12" stroke="{RED}"/>'
                 f'<text class="rl" x="{W - 28 - 46}" y="{y - 4}" text-anchor="middle">{esc(c["role"])}</text></g>')
    chars += c["name"] + c["role"]
    y += 24
    parts.append(f'<g class="ln" style="animation-delay:.8s"><text class="st" x="{tx}" y="{y}">{esc(c["subtitle"])} · organização e comunidade</text></g>')
    chars += c["subtitle"] + " · organização e comunidade"
    y += 28
    parts.append(f'<g class="ln" style="animation-delay:1.1s">' + "".join(
        f'<text class="ds" x="{tx}" y="{y + i * 18}">{esc(l)}</text>' for i, l in enumerate(wrap(c["description"], 66))) + "</g>")
    dl = wrap(c["description"], 66)
    chars += c["description"]
    y += len(dl) * 18 + 14
    cx = tx
    for k, f in enumerate(c["features"]):
        w = len(f) * 6.6 + 18
        if cx + w > W - 28:
            cx = tx; y += 28
        parts.append(f'<g class="chip" style="animation-delay:{1.6 + k * 0.2:.2f}s"><rect x="{cx:.1f}" y="{y}" width="{w:.1f}" height="22" rx="11" fill="{RED}" fill-opacity=".08" stroke="{RED}" stroke-opacity=".55"/>'
                     f'<text class="ch" x="{cx + w / 2:.1f}" y="{y + 15}" text-anchor="middle">{esc(f)}</text></g>')
        cx += w + 7
        chars += f
    y += 46
    links = [c["forum"].replace("https://", "").rstrip("/"), c["org"].replace("https://", "")]
    parts.append(f'<g class="ln" style="animation-delay:2.8s"><text class="lk" x="{tx}" y="{y}"><tspan class="ar">›</tspan> {esc(links[0])}'
                 f'<tspan dx="22" class="ar">›</tspan> {esc(links[1])}</text></g>')
    chars += "".join(links) + "›"
    H = int(max(H, y + 26))
    css = (f".t1{{fill:{TEXT};font-size:27px;font-weight:700}}.t2{{fill:{RED}}}.rl{{fill:{RED};font-size:12px;font-weight:700}}"
           f".st{{fill:{MUTED};font-size:12.5px}}.ds{{fill:{SOFT};font-size:12.5px}}.ch{{fill:#ffd6d6;font-size:11px}}"
           f".lk{{fill:{CYAN};font-size:12.5px}}.ar{{fill:{RED};font-weight:700}}"
           ".lg{opacity:0;animation:fi 1.4s .2s ease-out forwards}@keyframes fi{to{opacity:1}}"
           ".ln{opacity:0;animation:in .9s ease-out forwards}@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}"
           ".chip{opacity:0;animation:pop .6s ease-out forwards}@keyframes pop{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}")
    return window(W, H, f"{P}: ~$ cd ~/creative-zone && cat README.md", "".join(parts), style=css, chars=chars,
                  desc=f"{c['name']}: {c['description']}")


# ------------------------------------------------------------------ README

def badge(label: str, message: str, color: str, logo: str | None, logo_color="white") -> str:
    q = lambda s: s.replace("-", "--").replace("_", "__").replace(" ", "_")
    extra = f"&logo={logo}&logoColor={logo_color}" if logo else ""
    return f"https://img.shields.io/badge/{q(label)}-{q(message)}-{color}?style=for-the-badge{extra}"


def render_readme(cards: list[dict]) -> str:
    L, c = CONTENT["links"], CONTENT["community"]
    h = lambda cmd: f"<h3><code>{P} ~ $ {cmd}</code></h3>"
    rows = []
    for i in range(0, len(cards), 2):
        cells = []
        for pj in cards[i:i + 2]:
            img = f'<img src="./cards/{pj["slug"]}.svg" width="420" alt="{esc(pj["name"])}: {esc(pj["tagline"])}" />'
            cell = f'<a href="{pj["url"]}">{img}</a>' if pj["url"] else img
            cells.append(f'<td valign="top">{cell}</td>')
        rows.append("<tr>\n" + "\n".join(cells) + "\n</tr>")
    links = [
        f'[![LinkedIn]({badge("LinkedIn", L["linkedin_label"], "0A66C2", "linkedin")})]({L["linkedin"]})',
        f'[![Instagram]({badge("Instagram", L["instagram_label"], "E4405F", "instagram")})]({L["instagram"]})',
        f'[![E-mail]({badge("E-mail", L["email"], "EA4335", "gmail")})](mailto:{L["email"]})',
        f'[![Live Terminal]({badge("⚡ Live Terminal", "CREATIVE ZONE", "22d3ee", "gnometerminal", "black")})]({L["terminal"]})',
    ]
    cz = [
        f'[![Fórum]({badge("Fórum", c["forum"].replace("https://", "").rstrip("/"), "E11D2A", None)})]({c["forum"]})',
        f'[![GitHub]({badge("GitHub", c["org"].split("/")[-1], "161B22", "github")})]({c["org"]})',
    ]
    return f"""<!--
  Este README é gerado por scripts/render_static.py a partir de content/profile.json.
  Para mudar textos, projetos, stack ou links, edite content/profile.json: o GitHub Actions
  regenera este arquivo e os SVGs (os números de contribuição são atualizados todo dia).
-->

<div align="center">

<img src="./header.svg" width="860" alt="CREATIVE ZONE. {esc(CONTENT['name'])}, {esc(CONTENT['role'])} e {esc(CONTENT['founder_of'][0].lower() + CONTENT['founder_of'][1:])}" />

<br>
<br>

{h("whoami")}

<table>
<tr>
<td valign="top"><img src="./miguel-ascii.svg" width="420" alt="{esc(CONTENT['name'])}, retrato em ASCII gravado a laser" /></td>
<td valign="top"><img src="./about.svg" width="420" alt="Sobre: {esc(' '.join(CONTENT['about']['paragraphs']))}" /></td>
</tr>
</table>

<br>

{h("./contributions.sh")}

<img src="./contrib-heatmap.svg" width="860" alt="Gráfico de contribuições, atualizado diariamente" />

<img src="./stats.svg" width="860" alt="Sequência atual, maior sequência, total de contribuições, contribuições por mês e linguagens, atualizados diariamente" />

<br>
<br>

{h("ls ~/projetos")}

<table>
{chr(10).join(rows)}
</table>

<br>

{h("cat stack.json")}

<img src="./stack.svg" width="860" alt="Stack: {esc(', '.join(GROUP_LABEL.get(g, g) + ' (' + ', '.join(display_name(i) for i in its) + ')' for g, its in CONTENT['stack']))}" />

<br>
<br>

{h("cd ~/creative-zone")}

<a href="{c['forum']}"><img src="./community.svg" width="860" alt="{esc(c['name'])}: {esc(c['description'])}" /></a>

{chr(10).join(cz)}

<br>
<br>

{h("./snake.sh")}

<img src="./dist/snake.svg" width="860" alt="Cobrinha comendo o gráfico de contribuições" />

<br>
<br>

{h("./links.sh")}

{chr(10).join(links)}

<br>
<br>

<sub>tudo aqui é SVG gerado por código, animado sem JavaScript e atualizado todo dia pelo GitHub Actions</sub>

</div>
"""


def main():
    (ROOT / "header.svg").write_text(render_header(), encoding="utf-8")
    (ROOT / "about.svg").write_text(render_about(), encoding="utf-8")
    cards = CONTENT["projects"]
    hmax = max(card_height(p) for p in cards)
    (ROOT / "cards").mkdir(exist_ok=True)
    for pj in cards:
        (ROOT / "cards" / f"{pj['slug']}.svg").write_text(render_card(pj, hmax), encoding="utf-8")
    (ROOT / "stack.svg").write_text(render_stack(), encoding="utf-8")
    (ROOT / "community.svg").write_text(render_community(), encoding="utf-8")
    (ROOT / "README.md").write_text(render_readme(cards), encoding="utf-8")
    print(f"ok: header, about, {len(cards)} cards (h={hmax}), stack, community, README")


if __name__ == "__main__":
    main()
