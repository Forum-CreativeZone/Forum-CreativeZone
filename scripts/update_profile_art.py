"""Fetch real contribution data and render the profile art.

Writes (repo root):
  contrib-heatmap.svg  animated contribution graph (last 12 months)
  stats.svg            streak / totals card + contributions per month
  stats.json           same numbers, read by the live terminal site

Data source: GitHub GraphQL API when GH_TOKEN is set (in Actions the
built-in GITHUB_TOKEN is enough), otherwise the public contributions page.

usage: GH_LOGIN=Forum-CreativeZone GH_TOKEN=... python scripts/update_profile_art.py
       python scripts/update_profile_art.py --demo   (fake data, offline preview)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svgkit import (ROOT, window, font_face, fmt_int, FONT_STACK, BG, PANEL, BORDER,
                    TEXT, MUTED, DIM, GREEN, GREENS)

LOGIN = os.environ.get("GH_LOGIN", "Forum-CreativeZone")
PROMPT_USER = os.environ.get("PROMPT_USER", "miguel@creativezone")
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_CAP = [m.capitalize() for m in MESES]
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
UA = {"User-Agent": "creativezone-profile-art"}


# ---------------------------------------------------------------- data

def _graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={**UA, "Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


CAL_Q = """query($login:String!,$from:DateTime,$to:DateTime){
  user(login:$login){ name createdAt
    contributionsCollection(from:$from,to:$to){ contributionCalendar{ totalContributions
      weeks{ contributionDays{ date contributionCount contributionLevel } } } } } }"""


def fetch_graphql(token: str):
    d = _graphql(token, CAL_Q, {"login": LOGIN, "from": None, "to": None})["user"]
    name = d.get("name") or LOGIN
    year = [(day["date"], day["contributionCount"], LEVELS.get(day["contributionLevel"], 0))
            for w in d["contributionsCollection"]["contributionCalendar"]["weeks"]
            for day in w["contributionDays"]]
    # all-time history (one window per calendar year) for the longest streak
    created = dt.date.fromisoformat(d["createdAt"][:10])
    now = dt.datetime.now(dt.timezone.utc)
    history = {}
    for y in range(created.year, now.year + 1):
        frm = f"{y}-01-01T00:00:00Z"
        to = f"{y}-12-31T23:59:59Z" if y < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        c = _graphql(token, CAL_Q, {"login": LOGIN, "from": frm, "to": to})["user"]
        for w in c["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in w["contributionDays"]:
                history[day["date"]] = day["contributionCount"]
    for date, n, _ in year:
        history[date] = n
    return name, year, history


LANG_Q = """query($login:String!){ user(login:$login){
  repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){ nodes{ name
    languages(first:12, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } } } } } }"""
SKIP_REPOS = {LOGIN.lower(), f"{LOGIN.lower()}.github.io"}  # profile/site repos would skew the mix


def fetch_languages(token: str):
    nodes = _graphql(token, LANG_Q, {"login": LOGIN})["user"]["repositories"]["nodes"]
    agg = {}
    for r in nodes:
        if r["name"].lower() in SKIP_REPOS:
            continue
        for e in r["languages"]["edges"]:
            k = e["node"]["name"]
            a = agg.setdefault(k, {"name": k, "color": e["node"]["color"], "size": 0})
            a["size"] += e["size"]
    return sorted(agg.values(), key=lambda x: -x["size"])


TD_RE = re.compile(r'<td[^>]*?data-date="(\d{4}-\d{2}-\d{2})"[^>]*?id="([^"]+)"[^>]*?data-level="(\d)"', re.S)
TD_RE2 = re.compile(r'<td[^>]*?id="([^"]+)"[^>]*?data-date="(\d{4}-\d{2}-\d{2})"[^>]*?data-level="(\d)"', re.S)
TIP_RE = re.compile(r'<tool-tip[^>]*?for="([^"]+)"[^>]*>\s*([^<]*?)\s*</tool-tip>', re.S)


def _scrape(url: str):
    req = urllib.request.Request(url, headers={**UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    cells = {}
    for m in TD_RE.finditer(html):
        cells[m.group(2)] = (m.group(1), int(m.group(3)))
    for m in TD_RE2.finditer(html):
        cells.setdefault(m.group(1), (m.group(2), int(m.group(3))))
    tips = {m.group(1): m.group(2) for m in TIP_RE.finditer(html)}
    days = []
    for cid, (date, lvl) in cells.items():
        t = tips.get(cid, "")
        n = int(re.match(r"([\d,]+)", t).group(1).replace(",", "")) if re.match(r"[\d,]+ contribution", t) else 0
        days.append((date, n, lvl))
    days.sort()
    if not days:
        raise RuntimeError("no contribution cells found")
    return days


def fetch_scrape():
    base = f"https://github.com/users/{LOGIN}/contributions"
    year = _scrape(base)
    history = {d: n for d, n, _ in year}
    first = dt.date.fromisoformat(year[0][0])
    for y in range(first.year - 1, first.year - 6, -1):  # a few years back
        try:
            older = _scrape(f"{base}?from={y}-01-01&to={y}-12-31")
        except Exception:
            break
        if not any(n for _, n, _ in older):
            break
        for d, n, _ in older:
            history.setdefault(d, n)
    return LOGIN, year, history


def demo_data(empty=False):
    random.seed(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)
    year, history = [], {}
    d = start
    while d <= today:
        active = d >= today - dt.timedelta(days=60)
        n = random.choice([0, 0, 1, 2, 3, 5, 8, 13, 21, 34]) if active and not empty else 0
        lvl = 0 if n == 0 else 1 if n < 4 else 2 if n < 10 else 3 if n < 20 else 4
        year.append((d.isoformat(), n, lvl)); history[d.isoformat()] = n
        d += dt.timedelta(days=1)
    return "Miguel", year, history


# ---------------------------------------------------------------- numbers

def streaks(history: dict):
    days = sorted(history)
    if not days:
        return (0, None, None), (0, None, None)
    first, last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
    get = lambda d: history.get(d.isoformat(), 0)
    # longest
    best, run, run_start, best_rng = 0, 0, None, (None, None)
    d = first
    while d <= last:
        if get(d) > 0:
            run_start = run_start or d
            run += 1
            if run > best:
                best, best_rng = run, (run_start, d)
        else:
            run, run_start = 0, None
        d += dt.timedelta(days=1)
    # current: ends today, or yesterday if today has nothing yet
    end = last if get(last) > 0 else last - dt.timedelta(days=1)
    cur, d = 0, end
    while d >= first and get(d) > 0:
        cur += 1
        d -= dt.timedelta(days=1)
    cur_rng = (d + dt.timedelta(days=1), end) if cur else (None, None)
    return (cur, *cur_rng), (best, *best_rng)


def compute(name, year, history):
    total = sum(n for _, n, _ in year)
    active = sum(1 for _, n, _ in year if n > 0)
    best_day = max(year, key=lambda x: (x[1], x[0])) if year else ("", 0, 0)
    (cur, cs, ce), (lng, ls, le) = streaks(history)
    # contributions per month, last 13 calendar months of the window
    months = {}
    for d, n, _ in year:
        months[d[:7]] = months.get(d[:7], 0) + n
    keys = sorted(months)[-13:]
    iso = lambda x: x.isoformat() if x else None
    return {
        "login": LOGIN,
        "name": name,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": total,
        "active_days": active,
        "total_days": len(year),
        "current_streak": {"days": cur, "start": iso(cs), "end": iso(ce)},
        "longest_streak": {"days": lng, "start": iso(ls), "end": iso(le)},
        "best_day": {"count": best_day[1], "date": best_day[0]},
        "avg_per_active_day": round(total / active, 1) if active else 0,
        "months": [{"month": k, "label": MESES[int(k[5:]) - 1], "count": months[k]} for k in keys],
        "calendar": [{"date": d, "count": n, "level": l} for d, n, l in year],
    }


def br_date(s: str | None) -> str:
    if not s:
        return "-"
    d = dt.date.fromisoformat(s)
    return f"{d.day} {MESES[d.month - 1]}"


# ---------------------------------------------------------------- heatmap svg

def render_heatmap(st: dict) -> str:
    cal = st["calendar"]
    first = dt.date.fromisoformat(cal[0]["date"])
    sunday0 = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    step, cell, x0, y0 = 15.5, 12, 44, 40
    weeks = max((dt.date.fromisoformat(c["date"]) - sunday0).days // 7 for c in cal) + 1
    W = int(x0 + weeks * step + 22)
    H = 200
    rects, labels = [], []
    last_label_col = -9
    for c in cal:
        d = dt.date.fromisoformat(c["date"])
        col, row = (d - sunday0).days // 7, (d.weekday() + 1) % 7
        x, y = x0 + col * step, y0 + row * step
        delay = 0.4 + (col * 7 + row) * 0.011
        tip = f'{c["count"]} contribuições em {d.day:02d}/{d.month:02d}/{d.year}'
        rects.append(f'<rect class="c l{c["level"]}" x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="2.5" '
                     f'style="animation-delay:{delay:.3f}s"/>')
        if d.day <= 7 and row == 0 or (c is cal[0] and d.day <= 20):
            if col - last_label_col >= 3:
                labels.append(f'<text class="m" x="{x:.1f}" y="{y0 - 12}">{MESES_CAP[d.month - 1]}</text>')
                last_label_col = col
    days = "".join(f'<text class="m" x="{x0 - 8}" y="{y0 + r * step + 10}" text-anchor="end">{t}</text>'
                   for r, t in ((1, "Seg"), (3, "Qua"), (5, "Sex")))
    fy = y0 + 7 * step + 26
    legend_x = W - 22 - 5 * 15 - 40
    legend = (f'<text class="m" x="{legend_x - 8}" y="{fy}" text-anchor="end">Menos</text>' +
              "".join(f'<rect class="l{i}" x="{legend_x + i*15}" y="{fy - 10}" width="11" height="11" rx="2.5"/>' for i in range(5)) +
              f'<text class="m" x="{legend_x + 5*15 + 4}" y="{fy}">Mais</text>')
    total = (f'<text class="t" x="{x0}" y="{fy}"><tspan class="g">{fmt_int(st["total"])}</tspan> '
             f'contribuições no último ano</text>')
    lv = "".join(f".l{i}{{fill:{c}}}" for i, c in enumerate(GREENS))
    css = (font_face("0123456789 contribuiçõesnoúltimoanoMenosMaisSegQuaSex" + "".join(MESES_CAP) + fmt_int(st["total"]), (400, 700)) +
           f"text{{font-family:{FONT_STACK}}}{lv}.l0{{stroke:#21262d;stroke-width:1}}"
           f".m{{fill:{MUTED};font-size:11px}}.t{{fill:{TEXT};font-size:13px}}.g{{fill:{GREEN};font-weight:700}}"
           ".c{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .8s cubic-bezier(.2,1.5,.4,1) forwards}"
           "@keyframes pop{0%{opacity:0;transform:scale(.15)}100%{opacity:1;transform:scale(1)}}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Gráfico de contribuições de {escape(st['name'])}">
<title>{fmt_int(st['total'])} contribuições no último ano</title>
<style>{css}</style>
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="{BG}" stroke="{BORDER}"/>
{''.join(labels)}{days}
{''.join(rects)}
{total}{legend}
</svg>
"""


# ---------------------------------------------------------------- stats svg

def render_stats(st: dict) -> str:
    """Wide card (shown 1:1 at 860px) so every label stays readable."""
    W, pad, gap = 860, 20, 12
    langs = st.get("languages") or []
    H = 348 if langs else 278
    cs, ls = st["current_streak"], st["longest_streak"]
    pct = round(100 * st["active_days"] / st["total_days"]) if st["total_days"] else 0
    avg = f'{st["avg_per_active_day"]:.1f}'.replace(".", ",")
    tiles = [
        ("sequência atual", str(cs["days"]), "dias" if cs["days"] != 1 else "dia",
         f'{br_date(cs["start"])} - {br_date(cs["end"])}' if cs["days"] else "bora começar hoje", True),
        ("maior sequência", str(ls["days"]), "dias" if ls["days"] != 1 else "dia",
         f'{br_date(ls["start"])} - {br_date(ls["end"])}' if ls["days"] else "-", False),
        ("contribuições", fmt_int(st["total"]), "", "no último ano", False),
        ("dias ativos", str(st["active_days"]), f'/ {st["total_days"]}', f"{pct}% do ano", False),
        ("melhor dia", fmt_int(st["best_day"]["count"]), "", br_date(st["best_day"]["date"]), False),
        ("média / dia ativo", avg, "", "contribuições", False),
    ]
    tiles_w = 540
    tw, th = (tiles_w - 2 * gap) / 3, 101
    parts, chars = [], ""
    for i, (label, big, unit, sub, accent) in enumerate(tiles):
        x = pad + (i % 3) * (tw + gap)
        y = 46 + (i // 3) * (th + gap)
        delay = 0.4 + i * 0.28
        big_w = len(big) * 18.6  # 31px * 0.6
        parts.append(
            f'<g class="tile" style="animation-delay:{delay:.2f}s">'
            f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="{th}" rx="9" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<text class="lb" x="{x+14:.1f}" y="{y+24}"><tspan class="dl">$</tspan> {escape(label)}</text>'
            f'<text class="big{" ac" if accent else ""}" x="{x+14:.1f}" y="{y+62}">{escape(big)}</text>'
            + (f'<text class="un" x="{x+14+big_w+7:.1f}" y="{y+62}">{escape(unit)}</text>' if unit else "")
            + f'<text class="sb" x="{x+14:.1f}" y="{y+86}">{escape(sub)}</text></g>'
        )
        chars += label + big + unit + sub
    # contributions per month
    cx0 = pad + tiles_w + gap
    cw_ = W - pad - cx0
    cy, ch = 46, 2 * th + gap
    parts.append(f'<g class="tile" style="animation-delay:2.1s"><rect x="{cx0}" y="{cy}" width="{cw_}" height="{ch}" rx="9" fill="{PANEL}" stroke="{BORDER}"/>'
                 f'<text class="lb" x="{cx0+14}" y="{cy+24}"><tspan class="dl">$</tspan> contribuições / mês</text></g>')
    months = st["months"] or [{"label": "-", "count": 0}]
    mx = max(m["count"] for m in months) or 1
    n = len(months)
    area_x, area_w = cx0 + 12, cw_ - 24
    base_y, max_h = cy + ch - 30, ch - 86
    bw = area_w / n * 0.6
    for i, m in enumerate(months):
        bx = area_x + (i + 0.5) * area_w / n - bw / 2
        h = max(3, max_h * m["count"] / mx) if m["count"] else 3
        top = m["count"] == mx and m["count"] > 0
        delay = 2.4 + i * 0.16
        parts.append(f'<rect class="bar" style="animation-delay:{delay:.2f}s" x="{bx:.1f}" y="{base_y-h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2.5" '
                     f'fill="{GREEN if top else GREENS[3] if m["count"] else "#21262d"}"/>')
        parts.append(f'<text class="ml" x="{bx+bw/2:.1f}" y="{base_y+18}" text-anchor="middle">{m["label"][0].upper()}</text>')
        if top:
            parts.append(f'<text class="mv tile" style="animation-delay:{delay+.8:.2f}s" x="{bx+bw/2:.1f}" y="{base_y-h-8:.1f}" text-anchor="middle">{fmt_int(m["count"])}</text>')
            chars += fmt_int(m["count"])
        chars += m["label"].upper()
    # languages of public repositories
    if langs:
        ly = 46 + ch + gap
        lh = H - ly - 16
        total = sum(l["size"] for l in langs) or 1
        shown = langs[:6]
        parts.append(f'<g class="tile" style="animation-delay:4.6s"><rect x="{pad}" y="{ly}" width="{W-2*pad}" height="{lh}" rx="9" fill="{PANEL}" stroke="{BORDER}"/>'
                     f'<text class="lb" x="{pad+14}" y="{ly+24}"><tspan class="dl">$</tspan> linguagens nos repositórios públicos</text></g>')
        bx, bar_w, by = pad + 14, W - 2 * pad - 28, ly + 34
        acc = 0.0
        parts.append(f'<clipPath id="lbar"><rect x="{bx}" y="{by}" width="0" height="8" rx="4">'
                     f'<animate attributeName="width" from="0" to="{bar_w}" begin="4.9s" dur="1.8s" fill="freeze"/></rect></clipPath><g clip-path="url(#lbar)">')
        for l in langs:
            w = bar_w * l["size"] / total
            parts.append(f'<rect x="{bx+acc:.1f}" y="{by}" width="{w+0.5:.1f}" height="8" fill="{l.get("color") or "#8b949e"}"/>')
            acc += w
        parts.append("</g>")
        lx = bx
        for j, l in enumerate(shown):
            pctl = 100 * l["size"] / total
            label = f'{l["name"]} {pctl:.1f}%'.replace(".", ",")
            parts.append(f'<g class="tile" style="animation-delay:{5.4 + j*0.2:.2f}s"><circle cx="{lx+4}" cy="{by+24}" r="4" fill="{l.get("color") or "#8b949e"}"/>'
                         f'<text class="sb2" x="{lx+13}" y="{by+28}">{escape(label)}</text></g>')
            lx += 13 + len(label) * 7.2 + 22
            chars += label
    upd = dt.datetime.fromisoformat(st["generated_at"].replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=-3)))
    foot = f'atualizado {upd.day:02d}/{upd.month:02d}/{upd.year} {upd.hour:02d}:{upd.minute:02d}'
    parts.append(f'<text class="ft" x="{W-16}" y="20" text-anchor="end">{foot}</text>')
    chars += foot + "$ contribuições / mêslinguagens nos repositórios públicos"
    css = (".tile{opacity:0;animation:up 1.1s ease-out forwards}"
           "@keyframes up{0%{opacity:0;transform:translateY(6px)}100%{opacity:1;transform:translateY(0)}}"
           ".bar{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow 1.3s cubic-bezier(.2,.9,.3,1.1) forwards}"
           "@keyframes grow{to{transform:scaleY(1)}}"
           f".lb{{fill:{MUTED};font-size:12.5px}}.dl{{fill:{DIM}}}"
           f".big{{fill:{TEXT};font-size:31px;font-weight:700}}.ac{{fill:{GREEN}}}"
           f".un{{fill:{MUTED};font-size:13px}}.sb{{fill:{DIM};font-size:11.5px}}.sb2{{fill:#c9d1d9;font-size:12px}}"
           f".ml{{fill:{MUTED};font-size:11px}}.mv{{fill:{TEXT};font-size:11.5px;font-weight:700}}.ft{{fill:{DIM};font-size:10.5px}}")
    return window(W, H, f"{PROMPT_USER}: ~$ ./stats.sh", "\n".join(parts), style=css, chars=chars + "0123456789",
                  desc=f"Estatísticas de contribuição de {st['name']}")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="render with fake data (offline)")
    ap.add_argument("--placeholder", action="store_true", help="render an empty year (before the first real run)")
    args = ap.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.demo or args.placeholder:
        name, year, history = demo_data(empty=args.placeholder)
    else:
        try:
            if not token:
                raise RuntimeError("no token")
            name, year, history = fetch_graphql(token)
            print("source: graphql")
        except Exception as e:  # noqa: BLE001
            print(f"graphql unavailable ({e}); scraping public calendar")
            name, year, history = fetch_scrape()
            print("source: public page")
    st = compute(name, year, history)
    if args.demo:
        st["languages"] = [{"name": "JavaScript", "color": "#f1e05a", "size": 640}, {"name": "TypeScript", "color": "#3178c6", "size": 220},
                           {"name": "CSS", "color": "#663399", "size": 90}, {"name": "HTML", "color": "#e34c26", "size": 40}, {"name": "PLpgSQL", "color": "#336790", "size": 30}]
    elif not args.placeholder and token:
        try:
            st["languages"] = fetch_languages(token)
        except Exception as e:  # noqa: BLE001
            print(f"languages unavailable ({e})")
    (ROOT / "stats.json").write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "contrib-heatmap.svg").write_text(render_heatmap(st), encoding="utf-8")
    (ROOT / "stats.svg").write_text(render_stats(st), encoding="utf-8")
    print(f"{st['total']} contribuições | sequência {st['current_streak']['days']} | maior {st['longest_streak']['days']}")


if __name__ == "__main__":
    main()
