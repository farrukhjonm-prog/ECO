"""Graphic primitives for the ШОМИ КУЛОБ ad renderer.

Text rendering with Tajik-capable fonts (Montserrat / Oswald, OFL), gold
gradient fills, drop shadows, vector icons (phone, Instagram) and easing
curves.  All sizes are given in 1080-wide "design units" and multiplied by
the scale factor `s` so the same layout renders at 1080p or 4K.
"""
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent / "fonts"
GOLD = [(255, 236, 160), (232, 182, 82), (160, 104, 34)]
RED = (200, 24, 32)
WHITE = (255, 250, 242)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    """Clamp x into [a, b]."""
    return max(a, min(b, x))


def ease_out_cubic(x):
    """Fast start, gentle stop."""
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_out_back(x, k=1.6):
    """Overshoot then settle (used for icon/button pops)."""
    x = clamp(x)
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def ease_in_out_sine(x):
    """Symmetric smooth ease."""
    x = clamp(x)
    return 0.5 - 0.5 * np.cos(np.pi * x)


# ---------------------------------------------------------------- fonts
def font(name, size, weight):
    """Load a variable font at `size` px with the given wght axis value."""
    f = ImageFont.truetype(str(FONT_DIR / f"{name}-VF.ttf"), int(size))
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _gradient(w, h, stops):
    """Vertical multi-stop gradient as an RGB uint8 array (h, w, 3)."""
    ys = np.linspace(0, 1, h)[:, None]
    pos = np.linspace(0, 1, len(stops))
    cols = np.array(stops, dtype=float)
    out = np.stack([np.interp(ys[:, 0], pos, cols[:, c]) for c in range(3)], -1)
    return np.repeat(out[:, None, :], w, axis=1).astype(np.uint8)


def text_layer(text, fnt, fill, s, tracking=0, shadow=True, glow=None):
    """Render one line of text to a tight RGBA image.

    fill     -- RGB tuple, or "gold" for the brand gold gradient
    tracking -- extra letter spacing in design units
    glow     -- optional RGB colour of a soft outer glow
    """
    pad = int(40 * s)
    tr = tracking * s
    widths = [fnt.getlength(ch) for ch in text]
    total = sum(widths) + tr * max(0, len(text) - 1)
    asc, desc = fnt.getmetrics()
    W, H = int(total + 2 * pad), int(asc + desc + 2 * pad)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    x = pad
    for ch, w in zip(text, widths):
        d.text((x, pad), ch, font=fnt, fill=255)
        x += w + tr
    if fill == "gold":
        rgb = Image.fromarray(_gradient(W, H, [GOLD[0], GOLD[0], GOLD[1], GOLD[2]]))
    else:
        rgb = Image.new("RGB", (W, H), fill)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if glow:
        g = mask.filter(ImageFilter.GaussianBlur(14 * s)).point(lambda v: int(v * 0.55))
        layer = Image.composite(Image.new("RGBA", (W, H), glow + (255,)), layer, g)
        layer.putalpha(g)
    if shadow:
        sh = mask.filter(ImageFilter.GaussianBlur(6 * s)).point(lambda v: int(v * 0.75))
        sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sl.putalpha(sh)
        layer = Image.alpha_composite(layer, sl.transform(
            (W, H), Image.AFFINE, (1, 0, -3 * s, 0, 1, -5 * s)))
    top = rgb.convert("RGBA")
    top.putalpha(mask)
    return Image.alpha_composite(layer, top)


def rich_line(parts, s, gap=18):
    """Join several (text, font, fill) runs into one RGBA line image."""
    imgs = [text_layer(t, f, c, s) for t, f, c in parts]
    pad = int(40 * s)
    W = sum(i.width for i in imgs) - pad * 2 * (len(imgs) - 1) + int(gap * s) * (len(imgs) - 1)
    H = max(i.height for i in imgs)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = 0
    for i in imgs:
        out.alpha_composite(i, (x, (H - i.height) // 2))
        x += i.width - 2 * pad + int(gap * s)
    return out


# ---------------------------------------------------------------- shapes
def _ss(size, k=4):
    """Return a supersampled canvas size for anti-aliased vector drawing."""
    return size * k


def pill(text, fnt, s, bg=RED, fg=WHITE, padx=46, pady=26):
    """CTA button: rounded red pill with a thin gold border and white text."""
    tw = fnt.getlength(text)
    asc, desc = fnt.getmetrics()
    W, H = int(tw + 2 * padx * s), int(asc + desc + 2 * pady * s)
    k = 4
    big = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    r = H * k // 2
    d.rounded_rectangle((0, 0, W * k - 1, H * k - 1), r, fill=GOLD[1] + (255,))
    b = int(4 * s * k)
    d.rounded_rectangle((b, b, W * k - 1 - b, H * k - 1 - b), r - b, fill=bg + (255,))
    img = big.resize((W, H), Image.LANCZOS)
    ImageDraw.Draw(img).text(((W - tw) / 2, pady * s - desc * 0.15), text, font=fnt, fill=fg)
    return img


# Material Design "phone" glyph (Apache-2.0), 24x24 viewBox.
PHONE_PATH = ("M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 "
              "1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 "
              "0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z")


def _svg_points(path, steps=16):
    """Flatten a simple SVG path (M,c,C,l,L,h,H,v,V,z) into a point list."""
    toks = re.findall(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)", path)
    pts, i, cmd = [], 0, None
    x = y = 0.0
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "zZ":
                continue
        def num():
            nonlocal i
            v = float(toks[i])
            i += 1
            return v
        if cmd in "Mm":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if cmd == "m" else (nx, ny)
            pts.append((x, y))
            cmd = "l" if cmd == "m" else "L"
        elif cmd in "Ll":
            nx, ny = num(), num()
            x, y = (x + nx, y + ny) if cmd == "l" else (nx, ny)
            pts.append((x, y))
        elif cmd in "Hh":
            v = num()
            x = x + v if cmd == "h" else v
            pts.append((x, y))
        elif cmd in "Vv":
            v = num()
            y = y + v if cmd == "v" else v
            pts.append((x, y))
        elif cmd in "Cc":
            c = [num() for _ in range(6)]
            if cmd == "c":
                c = [c[0] + x, c[1] + y, c[2] + x, c[3] + y, c[4] + x, c[5] + y]
            for k in range(1, steps + 1):
                t = k / steps
                mt = 1 - t
                px = mt**3 * x + 3 * mt**2 * t * c[0] + 3 * mt * t**2 * c[2] + t**3 * c[4]
                py = mt**3 * y + 3 * mt**2 * t * c[1] + 3 * mt * t**2 * c[3] + t**3 * c[5]
                pts.append((px, py))
            x, y = c[4], c[5]
        else:
            i += 1
    return pts


def phone_icon(size):
    """Gold circular badge with a white telephone handset (vector-drawn)."""
    k = 4
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, S - 1, S - 1), fill=GOLD[1] + (255,))
    d.ellipse((S * 0.04, S * 0.04, S * 0.96, S * 0.96), fill=(150, 18, 26, 255))
    hand = Image.new("L", (S, S), 0)
    pts = [(x * S * 0.52 / 24 + S * 0.24, y * S * 0.52 / 24 + S * 0.24) for x, y in _svg_points(PHONE_PATH)]
    ImageDraw.Draw(hand).polygon(pts, fill=255)
    img.paste(Image.new("RGBA", (S, S), WHITE + (255,)), (0, 0), hand)
    return img.resize((size, size), Image.LANCZOS)


def insta_icon(size):
    """Instagram-style glyph: gradient rounded square, ring and dot."""
    k = 4
    S = size * k
    grad = np.zeros((S, S, 3), np.uint8)
    yy, xx = np.mgrid[0:S, 0:S] / S
    t = np.clip((xx + (1 - yy)) / 2, 0, 1)[..., None]
    c1, c2, c3 = np.array([254, 218, 117]), np.array([214, 41, 118]), np.array([79, 91, 213])
    grad = np.where(t < 0.5, c1 + (c2 - c1) * (t / 0.5), c2 + (c3 - c2) * ((t - 0.5) / 0.5))
    base = Image.fromarray(grad.astype(np.uint8)).convert("RGBA")
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), S * 0.26, fill=255)
    base.putalpha(m)
    d = ImageDraw.Draw(base)
    lw = int(S * 0.075)
    o = S * 0.2
    d.rounded_rectangle((o, o, S - o, S - o), S * 0.17, outline=WHITE + (255,), width=lw)
    r = S * 0.16
    d.ellipse((S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r), outline=WHITE + (255,), width=lw)
    r2 = S * 0.045
    d.ellipse((S * 0.69 - r2, S * 0.31 - r2, S * 0.69 + r2, S * 0.31 + r2), fill=WHITE + (255,))
    return base.resize((size, size), Image.LANCZOS)


def ring(size, width):
    """Thin gold ring used for the pulsing halo behind icons."""
    k = 4
    S = size * k
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, S - 1, S - 1), outline=GOLD[0] + (255,),
                                width=int(width * k))
    return img.resize((size, size), Image.LANCZOS)


def ornament(width, s):
    """Gold divider: two hairlines with a centre diamond."""
    H = int(30 * s)
    k = 4
    img = Image.new("RGBA", (width * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy, cx = H * k / 2, width * k / 2
    lw = max(1, int(2.2 * s * k))
    d.line((0, cy, cx - 30 * s * k, cy), fill=GOLD[1] + (255,), width=lw)
    d.line((cx + 30 * s * k, cy, width * k, cy), fill=GOLD[1] + (255,), width=lw)
    r = 11 * s * k
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=GOLD[0] + (255,))
    return img.resize((width, H), Image.LANCZOS)


def with_alpha(img, a):
    """Return a copy of RGBA `img` with its alpha multiplied by a in [0,1]."""
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


def panel(w, h, s, alpha=150):
    """Soft dark 'glass' card placed behind text over busy photos."""
    m = int(40 * s)
    W, H = int(w * s) + 2 * m, int(h * s) + 2 * m
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((m, m, W - m, H - m), int(34 * s), fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(16 * s))
    img = Image.new("RGBA", (W, H), (12, 5, 4, 0))
    img.putalpha(mask)
    return img
