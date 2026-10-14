"""Shared helpers for the profile SVGs: embedded mono font + terminal window chrome.

Fonts can't be loaded from the network inside an <img>-rendered SVG, so a
subset of JetBrains Mono (SIL OFL 1.1, see assets/JetBrainsMono-OFL.txt)
is embedded as base64 woff2 with only the glyphs each SVG actually uses.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

FONT_FILES = {
    400: ASSETS / "jetbrains-mono-latin-400-normal.woff2",
    700: ASSETS / "jetbrains-mono-latin-700-normal.woff2",
}
FONT_STACK = "'CZ Mono', 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"

# palette (GitHub dark + CREATIVE ZONE accent)
BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
DIM = "#6e7681"
GREEN = "#39d353"
GREENS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]


def font_face(chars: str, weights=(400, 700)) -> str:
    """Return @font-face rules with a glyph subset limited to `chars`."""
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:  # still renders with the fallback stack
        return ""
    text = "".join(sorted(set(chars + " ")))
    rules = []
    for w in weights:
        src = FONT_FILES.get(w)
        if not src or not src.exists():
            continue
        font = TTFont(str(src))
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = []
        opts.hinting = False
        opts.name_IDs = []
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        rules.append(
            "@font-face{font-family:'CZ Mono';font-weight:%d;"
            "src:url(data:font/woff2;base64,%s) format('woff2');}" % (w, b64)
        )
    return "".join(rules)


def window(width: int, height: int, title: str, body: str, style: str = "",
           chars: str = "", desc: str = "") -> str:
    """Wrap `body` in a dark terminal window (traffic lights + title bar)."""
    used = chars + title
    css = font_face(used) + style
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(desc or title)}">
<title>{escape(desc or title)}</title>
<style>{css}
text{{font-family:{FONT_STACK};}}
.ttl{{fill:{MUTED};font-size:11px;}}
</style>
<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="12" fill="{BG}" stroke="{BORDER}"/>
<path d="M12.5 0.5h{width-25}a12 12 0 0 1 12 12v19.5h-{width-1}v-19.5a12 12 0 0 1 12-12z" fill="{PANEL}"/>
<line x1="0.5" y1="32" x2="{width-0.5}" y2="32" stroke="{BORDER}"/>
<circle cx="20" cy="16" r="5.5" fill="#ff5f57"/><circle cx="38" cy="16" r="5.5" fill="#febc2e"/><circle cx="56" cy="16" r="5.5" fill="#28c840"/>
<text class="ttl" x="{width/2}" y="20" text-anchor="middle">{escape(title)}</text>
{body}
</svg>
"""


def fmt_int(n: int) -> str:
    """1234567 -> '1.234.567' (pt-BR)."""
    return f"{int(n):,}".replace(",", ".")
