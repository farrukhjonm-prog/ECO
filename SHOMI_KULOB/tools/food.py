"""Food-ad scene builders: official-logo intro, dish cards, logo end screen.

Dish names, portions and prices are passed through from project.json
*verbatim* (they must be copied exactly from the menu file); this module
never edits, translates or re-cases them beyond what the JSON says.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import cutout
import gfx

ROOT = Path(__file__).resolve().parent.parent
_CACHE = {}


def logo(path, width):
    """Official logo, external background removed, scaled to `width` px."""
    key = (path, width)
    if key not in _CACHE:
        lg = cutout.logo_cutout(ROOT / path)
        _CACHE[key] = lg.resize((width, int(lg.height * width / lg.width)), Image.LANCZOS)
    return _CACHE[key]


def price_badge(portion, amount, currency, s, d=270):
    """Red round price badge with gold ring: portion / amount / currency."""
    k = 3
    D = int(d * s)
    big = Image.new("RGBA", (D * k, D * k), (0, 0, 0, 0))
    dr = ImageDraw.Draw(big)
    dr.ellipse((0, 0, D * k - 1, D * k - 1), fill=gfx.GOLD[1] + (255,))
    r = int(7 * s * k)
    dr.ellipse((r, r, D * k - 1 - r, D * k - 1 - r), fill=(196, 20, 28, 255))
    img = big.resize((D, D), Image.LANCZOS)
    sh = Image.new("RGBA", (D + int(40 * s), D + int(40 * s)), (0, 0, 0, 0))
    m = Image.new("L", sh.size, 0)
    ImageDraw.Draw(m).ellipse((int(20 * s), int(28 * s), D + int(20 * s), D + int(28 * s)), fill=150)
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(10 * s)))
    sh.alpha_composite(img, (int(20 * s), int(20 * s)))
    cx = sh.width / 2
    y = int(20 * s) + D * 0.5
    for txt, size, wgt, dy in ((portion, 34, 600, -0.30), (amount, 118, 700, 0.0),
                               (currency, 34, 700, 0.30)):
        f = gfx.font("Oswald", size * s, wgt)
        layer = gfx.text_layer(txt, f, gfx.WHITE, s, shadow=False)
        sh.alpha_composite(layer, (int(cx - layer.width / 2), int(y + dy * D - layer.height / 2)))
    return sh


def steam_texture(w, h, s, seed=3):
    """Tall soft wisp texture (scrolled upward per frame for rising steam)."""
    rng = np.random.default_rng(seed)
    H2 = h * 2
    acc = np.zeros((H2, w), np.float32)
    for _ in range(7):
        x0 = rng.uniform(0.2, 0.8) * w
        ph = rng.uniform(0, 6.28)
        ys = np.arange(H2)
        xs = x0 + 40 * s * np.sin(ys / (90 * s) + ph)
        wid = rng.uniform(14, 30) * s
        xx = np.arange(w)[None, :]
        band = np.exp(-((xx - xs[:, None]) / wid) ** 2)
        acc += band * (0.5 + 0.5 * np.sin(ys / (160 * s) + ph))[:, None]
    acc = np.clip(acc / acc.max(), 0, 1)
    a = Image.fromarray((acc * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(8 * s))
    # fade horizontally to avoid hard edges
    fx = np.clip(np.minimum(np.arange(w), w - np.arange(w)) / (0.25 * w), 0, 1)
    arr = np.asarray(a, np.float32) * fx[None, :] * 0.55
    img = Image.new("RGBA", (w, H2), (255, 245, 235, 0))
    img.putalpha(Image.fromarray(arr.astype(np.uint8)))
    return img


def logo_intro(els, sc, s):
    """Official logo zooms in with a specular sweep."""
    t0, t1 = sc["start"], sc["end"]
    lg = logo(sc["logo"], int(sc.get("logo_w", 660) * s))
    els.append(dict(img=gfx.ring(int(700 * s), 3 * s), cx=540, cy=900, t0=t0 + 0.5, t1=t1 - 0.3,
                    anim="pulse", din=1.5))
    els.append(dict(img=lg, cx=540, cy=900, t0=t0 + 0.1, t1=t1 - 0.3, anim="zoom", din=1.0,
                    shine=(t0 + 0.9, 0.8)))


def dish(els, sc, s):
    """One menu item: name, cut-out photo with steam, price badge."""
    t0, t1 = sc["start"], sc["end"]
    c = sc["cut"]
    img = cutout.dish_cutout(ROOT / c["src"], c["box"], c["ellipse"], int(c.get("w", 1000) * s))
    tex = steam_texture(int(600 * s), int(420 * s), s, seed=int(t0 * 10))
    els.append(dict(img=tex, cx=540, cy=c.get("steam_cy", 700), t0=t0 + 0.4, t1=t1 - 0.3,
                    anim="steam", din=0.8, h=int(420 * s)))
    els.append(dict(img=img, cx=540, cy=c.get("cy", 930), t0=t0, t1=t1 - 0.3, anim="slide",
                    din=0.55, push=0.018))
    if sc.get("index"):
        idx = gfx.pill(sc["index"], gfx.font("Oswald", 40 * s, 700), s, padx=26, pady=8)
        els.append(dict(img=idx, cx=540, cy=325, t0=t0 + 0.05, t1=t1 - 0.3, anim="pop", din=0.4))
    n = len(sc["name"])
    size = sc.get("name_size", 100)
    for i, line in enumerate(sc["name"]):
        f = gfx.font("Oswald", size * s, 700)
        while f.getlength(line) > 880 * s and f.size > 40:
            f = gfx.font("Oswald", f.size - 4, 700)
        lay = gfx.text_layer(line, f, gfx.WHITE if i == 0 or n == 1 else gfx.WHITE, s,
                             glow=(255, 110, 30))
        els.append(dict(img=lay, cx=540, cy=505 + (i - (n - 1) / 2) * size * 1.08,
                        t0=t0 + 0.15 + 0.1 * i, t1=t1 - 0.3, anim="rise", din=0.5))
    p = sc["price"]
    badge = price_badge(p["portion"], p["amount"], p["currency"], s)
    els.append(dict(img=badge, cx=p.get("cx", 810), cy=p.get("cy", 1190), t0=t0 + 0.4,
                    t1=t1 - 0.3, anim="pop", din=0.5))


def strip(els, sc, s):
    """Small persistent order strip (phone icon + number) under dish cards."""
    t0, t1 = sc["start"], sc["end"]
    ic = gfx.phone_icon(int(64 * s))
    f = gfx.font("Oswald", 56 * s, 600)
    txt = gfx.rich_line([("Фармоиш:", gfx.font("Montserrat", 40 * s, 700), "gold"),
                         ("+992 934 41 41 41", f, gfx.WHITE)], s, gap=16)
    pad = int(40 * s)
    W = ic.width + int(18 * s) + txt.width - pad
    comb = Image.new("RGBA", (W + 2 * pad, max(ic.height, txt.height)), (0, 0, 0, 0))
    comb.alpha_composite(ic, (pad, (comb.height - ic.height) // 2))
    comb.alpha_composite(txt, (ic.width + int(18 * s), (comb.height - txt.height) // 2))
    els.append(dict(img=gfx.panel(W / s + 20, 92, s, alpha=170), cx=540, cy=sc.get("cy", 1420),
                    t0=t0, t1=t1 - 0.3, anim="fade", din=0.4))
    els.append(dict(img=comb, cx=540, cy=sc.get("cy", 1420), t0=t0 + 0.1, t1=t1 - 0.3,
                    anim="fade", din=0.4))
