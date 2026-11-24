"""Frame renderer for ШОМИ КУЛОБ vertical (9:16) ads.

Takes one *variant* of a project (duration + scene list, see
06_PROJECTS/*/project.json) and renders it to H.264 video segments in
parallel.  Visual layers, back to front:

  1. background (quarter-res, upscaled): warm gradient, drifting light
     leaks, rising smoke, vignette, beat-synced light-streak on cuts
  2. embers (half-res gaussian splats, sub-pixel smooth, no aliasing)
  3. film grain
  4. graphics: wordmark, kinetic text lines, CTA, icons, contacts

Everything is a pure function of time t, so renders are deterministic and
free of jitter.  Design units are 1080-wide; `s` scales them.
"""
import subprocess
from multiprocessing import Pool

import numpy as np
from PIL import Image

import food
import gfx
import photo

FPS = 30
_STATE = {}


# ------------------------------------------------------------ scene build
def _fit(text, family, size, weight, maxw, s, tracking=0):
    """Largest font <= size whose rendered line width fits maxw (design px)."""
    while size > 20:
        f = gfx.font(family, size * s, weight)
        w = sum(f.getlength(c) for c in text) + tracking * s * (len(text) - 1)
        if w <= maxw * s:
            return f
        size -= 2
    return gfx.font(family, size * s, weight)


COLORS = {"w": gfx.WHITE, "gold": "gold", "red": (235, 50, 50)}


def build_elements(variant, s):
    """Turn the scene list into timed graphic elements (pre-rendered RGBA)."""
    els = []
    maxw = 860
    for sc in variant["scenes"]:
        t0, t1, kind = sc["start"], sc["end"], sc["type"]
        if kind == "intro":
            lab = gfx.text_layer("Р Е С Т О Р А Н", gfx.font("Montserrat", 30 * s, 600),
                                 "gold", s, shadow=False)
            els.append(dict(img=lab, cx=540, cy=800, t0=t0 + 0.5, t1=t1 - 0.35,
                            anim="fade", din=0.7))
            f = _fit("ШОМИ КУЛОБ", "Montserrat", 128, 900, maxw, s, 4)
            wm = gfx.text_layer("ШОМИ КУЛОБ", f, "gold", s, tracking=4, glow=(255, 140, 40))
            els.append(dict(img=wm, cx=540, cy=900, t0=t0 + 0.15, t1=t1 - 0.35,
                            anim="zoom", din=1.3, shine=(t0 + 1.1, 0.9)))
            orn = gfx.ornament(int(560 * s), s)
            els.append(dict(img=orn, cx=540, cy=1010, t0=t0 + 0.8, t1=t1 - 0.35,
                            anim="grow", din=0.8))
        elif kind == "lines":
            size = sc.get("size", 92)
            lh = size * 1.22
            n = len(sc["lines"])
            y0 = sc.get("cy", 900) - lh * (n - 1) / 2
            line_els = []
            for i, runs in enumerate(sc["lines"]):
                txt = " ".join(r[0] for r in runs)
                big = runs[0][2] if len(runs[0]) > 2 else size
                f = _fit(txt, "Montserrat", big, 800, maxw, s)
                img = gfx.rich_line([(r[0], f, COLORS[r[1]]) for r in runs], s,
                                    gap=f.size / s * 0.28)
                line_els.append(dict(img=img, cx=540, cy=y0 + i * lh, t0=t0 + 0.12 + 0.13 * i,
                                     t1=t1 - 0.35, anim="rise", din=0.6))
            if sc.get("panel"):
                pw = max(e["img"].width for e in line_els) / s - 40
                ph = lh * n + 40
                els.append(dict(img=gfx.panel(pw, ph, s), cx=540, cy=sc.get("cy", 900),
                                t0=t0, t1=t1 - 0.35, anim="fade", din=0.4))
            els += line_els
        elif kind == "brandbug":
            bug = gfx.text_layer("ШОМИ КУЛОБ", gfx.font("Montserrat", 34 * s, 800), "gold",
                                 s, tracking=10)
            els.append(dict(img=bug, cx=540, cy=330, t0=t0, t1=t1 - 0.35, anim="fade", din=0.5))
        elif kind == "end":
            _end_screen(els, sc, s, maxw)
        elif kind == "logo_intro":
            food.logo_intro(els, sc, s)
        elif kind == "dish":
            food.dish(els, sc, s)
        elif kind == "strip":
            food.strip(els, sc, s)
    return els


def _end_screen(els, sc, s, maxw):
    """Final branded contact screen (settles within 1 s, then stationary)."""
    t0, t1 = sc["start"], sc["end"]
    oy = sc.get("oy", 60)
    if sc.get("logo"):
        lg = food.logo(sc["logo"], int(sc.get("logo_w", 400) * s))
        els.append(dict(img=lg, cx=540, cy=sc.get("logo_cy", 470) + oy, t0=t0, t1=t1,
                        anim="zoom", din=0.8, shine=(t0 + 0.9, 0.9)))
    else:
        lab = gfx.text_layer("Р Е С Т О Р А Н", gfx.font("Montserrat", 30 * s, 600), "gold", s,
                             shadow=False)
        els.append(dict(img=lab, cx=540, cy=400 + oy, t0=t0, t1=t1, anim="fade", din=0.5))
        f = _fit("ШОМИ КУЛОБ", "Montserrat", 116, 900, maxw, s, 4)
        wm = gfx.text_layer("ШОМИ КУЛОБ", f, "gold", s, tracking=4, glow=(255, 140, 40))
        els.append(dict(img=wm, cx=540, cy=495 + oy, t0=t0, t1=t1, anim="zoom", din=0.8,
                        shine=(t0 + 0.9, 0.9)))
        els.append(dict(img=gfx.ornament(int(520 * s), s), cx=540, cy=595 + oy, t0=t0 + 0.2,
                        t1=t1, anim="grow", din=0.6))
    cta = "ҲАМИН ҲОЛО ФАРМОИШ ДИҲЕД!"
    pf = _fit(cta, "Oswald", 56, 700, maxw - 100, s)
    els.append(dict(img=gfx.pill(cta, pf, s), cx=540, cy=715 + oy, t0=t0 + 0.3, t1=t1,
                    anim="pop", din=0.6))
    ph = gfx.phone_icon(int(118 * s))
    els.append(dict(img=gfx.ring(int(118 * s), 3 * s), cx=540, cy=880 + oy, t0=t0 + 1.0,
                    t1=t1, anim="pulse", din=1.6))
    els.append(dict(img=ph, cx=540, cy=880 + oy, t0=t0 + 0.45, t1=t1, anim="pop", din=0.55))
    num = "+992 934 41 41 41"
    nf = _fit(num, "Oswald", 124, 700, maxw, s)
    els.append(dict(img=gfx.text_layer(num, nf, gfx.WHITE, s, glow=(255, 120, 40)), cx=540,
                    cy=1030 + oy, t0=t0 + 0.55, t1=t1, anim="rise", din=0.5))
    handle = "@shomi_kulob_restourant"
    hf = _fit(handle, "Montserrat", 46, 700, maxw - 110, s)
    row = gfx.rich_line([(handle, hf, gfx.WHITE)], s)
    ic = gfx.insta_icon(int(74 * s))
    pad = int(40 * s)
    W = ic.width + int(20 * s) + row.width - pad
    comb = Image.new("RGBA", (W + 2 * pad, max(ic.height, row.height)), (0, 0, 0, 0))
    comb.alpha_composite(ic, (pad, (comb.height - ic.height) // 2))
    comb.alpha_composite(row, (pad + ic.width + int(20 * s) - pad, (comb.height - row.height) // 2))
    els.append(dict(img=comb, cx=540, cy=1185 + oy, t0=t0 + 0.7, t1=t1, anim="rise", din=0.5))


# ------------------------------------------------------------ background
def _init(W, H, variant, seed):
    """Per-worker precomputation (textures, particles, graphics)."""
    s = W / 1080
    rng = np.random.default_rng(seed)
    lw, lh = W // 4, H // 4
    yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
    yy /= lh
    xx /= lw
    top, bot = np.array([26, 9, 8], np.float32), np.array([7, 3, 3], np.float32)
    base = top + (bot - top) * yy[..., None]
    r = np.sqrt((xx - 0.5) ** 2 + ((yy - 0.52) * 1.2) ** 2)
    base += np.array([56, 17, 8], np.float32) * np.exp(-(r / 0.38) ** 2)[..., None]
    vig = (1 - 0.65 * np.clip(r / 0.75, 0, 1) ** 2.2)[..., None]
    # Fractal smoke texture, twice the height for vertical scrolling.
    smoke = np.zeros((lh * 2, lw), np.float32)
    for oct_, amp in ((6, 1.0), (12, 0.5), (24, 0.25)):
        small = rng.random((oct_ * 4, oct_ * 2)).astype(np.float32)
        im = Image.fromarray((small * 255).astype(np.uint8)).resize((lw, lh * 2), Image.BICUBIC)
        smoke += np.asarray(im, np.float32) / 255 * amp
    smoke = np.clip((smoke / 1.75 - 0.45) * 2.2, 0, 1) ** 1.6
    smoke = np.concatenate([smoke, smoke], 0)
    grain = rng.normal(0, 4.0, (H + 64, W + 64)).astype(np.float32)
    n = 110
    parts = dict(x=rng.random(n), P=rng.uniform(5, 11, n), ph=rng.random(n),
                 sw=rng.uniform(0.01, 0.04, n), sp=rng.uniform(1.5, 4, n),
                 sz=rng.uniform(0.6, 2.2, n), br=rng.uniform(0.5, 1.0, n),
                 fl=rng.uniform(2, 6, n))
    cuts = [sc["start"] for sc in variant["scenes"] if sc["type"] not in ("brandbug", "strip")
            and sc["start"] > 0]
    els = build_elements(variant, s)
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    k = 4
    fr = Image.new("L", (W, H), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(fr).rectangle((44 * s, 44 * s, W - 44 * s, H - 44 * s),
                                 outline=150, width=max(1, int(2 * s)))
    frame = Image.new("RGBA", (W, H), gfx.GOLD[1] + (0,))
    frame.putalpha(fr)
    _STATE.update(W=W, H=H, s=s, base=base, vig=vig, smoke=smoke, xx=xx, yy=yy,
                  grain=grain, parts=parts, cuts=cuts, els=els, rng=rng, frame=frame,
                  dur=variant["duration"],
                  photos=photo.PhotoTrack(variant, W, H)
                  if any("photo" in sc for sc in variant["scenes"]) else None)


def _background(t):
    """Quarter-res background + half-res embers composited at full res."""
    st = _STATE
    xx, yy = st["xx"], st["yy"]
    img = st["base"].copy()
    leaks = ((0.25 + 0.15 * np.sin(t * 0.31), 0.30 + 0.10 * np.cos(t * 0.23), 0.30,
              (255, 120, 30), 0.15),
             (0.80 + 0.10 * np.cos(t * 0.27), 0.72 + 0.08 * np.sin(t * 0.19), 0.34,
              (190, 25, 20), 0.21),
             (0.55 + 0.20 * np.sin(t * 0.17 + 1), 0.95, 0.40, (255, 90, 20), 0.13))
    for cx, cy, rad, col, a in leaks:
        g = np.exp(-(((xx - cx) ** 2 + ((yy - cy) * 0.56) ** 2) / rad ** 2))
        img += np.array(col, np.float32) * (a * g)[..., None]
    lh = img.shape[0]
    off = int((t * 0.045 * lh) % (lh * 2))
    sm = st["smoke"][off:off + lh] * (0.35 + 0.65 * yy)
    img += np.array([90, 60, 45], np.float32) * (0.22 * sm)[..., None]
    img *= st["vig"]
    W, H = st["W"], st["H"]
    ph = st.get("photos")
    if ph is not None and ph.active(t):
        out = ph.frame(t)
        gain = ph.ember_gain(t)
    else:
        bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        out = np.asarray(bg, np.float32).copy()
        gain = 1.0
    for c in st["cuts"]:
        d = t - c
        if -0.22 < d < 0.22:
            band = np.exp(-(((xx + yy * 0.55) - (0.2 + (d + 0.22) / 0.44 * 1.6)) / 0.09) ** 2)
            sk = np.clip(band * (1 - abs(d) / 0.22) * 0.55 * 255, 0, 255).astype(np.uint8)
            sk = np.asarray(Image.fromarray(sk).resize((W, H), Image.BICUBIC), np.float32) / 255
            out += np.array([255, 190, 110], np.float32) * sk[..., None]
    if gain > 0:
        out += _embers(t) * gain
    fr = np.random.default_rng(int(round(t * FPS)) + 7)
    gy, gx = int(fr.integers(0, 64)), int(fr.integers(0, 64))
    out += st["grain"][gy:gy + H, gx:gx + W][..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def _embers(t):
    """Rising glowing embers rendered as sub-pixel gaussian splats."""
    st = _STATE
    W, H, p = st["W"] // 2, st["H"] // 2, st["parts"]
    acc = np.zeros((H, W), np.float32)
    life = (t / p["P"] + p["ph"]) % 1.0
    ys = (1.06 - life * 1.2) * H
    xs = (p["x"] + p["sw"] * np.sin(2 * np.pi * t / p["sp"] + p["ph"] * 9)) * W
    fade = np.sin(np.pi * life) ** 1.5
    flick = 0.75 + 0.25 * np.sin(t * p["fl"] + p["ph"] * 20)
    sc = st["s"] / 2
    for x, y, sz, b in zip(xs, ys, p["sz"] * sc * 3, p["br"] * fade * flick):
        r = int(sz * 4) + 2
        xi, yi = int(x), int(y)
        if xi < -r or yi < -r or xi >= W + r or yi >= H + r:
            continue
        x0, x1, y0, y1 = max(0, xi - r), min(W, xi + r + 1), max(0, yi - r), min(H, yi + r + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        gx = np.arange(x0, x1) - x
        gy = np.arange(y0, y1) - y
        d2 = gy[:, None] ** 2 + gx[None, :] ** 2
        acc[y0:y1, x0:x1] += b * (np.exp(-d2 / (2 * sz ** 2)) + 0.25 * np.exp(-d2 / (2 * (sz * 3) ** 2)))
    col = np.array([255, 150, 55], np.float32) / 255
    e = Image.fromarray(np.clip(acc * 255, 0, 255).astype(np.uint8)).resize(
        (st["W"], st["H"]), Image.BILINEAR)
    return np.asarray(e, np.float32)[..., None] * col


# ------------------------------------------------------------ compositing
def _place(frame, el, t):
    """Composite one animated element onto the frame at time t."""
    s = _STATE["s"]
    t0, t1, din = el["t0"], el["t1"], el["din"]
    if t < t0:
        return
    p = (t - t0) / din
    a, dy, sc = 1.0, 0.0, 1.0
    dx_slide = 0.0
    img = el["img"]
    anim = el["anim"]
    if anim == "fade":
        a = gfx.ease_in_out_sine(p)
    elif anim == "zoom":
        e = gfx.ease_out_cubic(p)
        a, sc = e, 1.10 - 0.10 * e
    elif anim == "pop":
        a, sc = gfx.ease_out_cubic(p * 1.6), 0.55 + 0.45 * gfx.ease_out_back(p)
    elif anim == "grow":
        e = gfx.ease_out_cubic(p)
        w = max(1, int(img.width * e))
        img = img.crop(((img.width - w) // 2, 0, (img.width + w) // 2, img.height))
    elif anim == "slide":
        e = gfx.ease_out_cubic(p)
        a = min(1.0, p * 2)
        sc = (0.86 + 0.14 * e) * (1 + el.get("push", 0) * max(0.0, t - t0))
        dx_slide = (1 - e) * 620 * s
    elif anim == "hero":
        e = gfx.ease_in_out_sine(p)
        a = min(1.0, (t - t0) / 0.3)
        sc = el["zoom0"] + (1 - el["zoom0"]) * e
        sc *= 1 + el.get("push", 0) * max(0.0, t - t0 - din)
    elif anim == "steam":
        a = gfx.ease_in_out_sine(p) * 0.9
        hh = el["h"]
        off = int((t * 60 * s) % (img.height - hh))
        img = img.crop((0, img.height - hh - off, img.width, img.height - off))
    elif anim == "pulse":
        cyc = ((t - t0) % din) / din
        a, sc = 0.7 * (1 - cyc) ** 1.5, 1.0 + 0.55 * gfx.ease_out_cubic(cyc)
    if t1 is not None and t >= t1:
        q = gfx.ease_in_out_sine((t - t1) / 0.32)
        if q >= 1:
            return
        a *= 1 - q
        dy -= 36 * s * q
    if el.get("shine"):
        img = _shine(img, t, *el["shine"])
    if sc != 1.0:
        img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))),
                         Image.BICUBIC)
    x = int(el["cx"] * s - img.width / 2 + dx_slide)
    y = int(el["cy"] * s - img.height / 2 + dy)
    if anim == "rise":
        e = gfx.ease_out_cubic(p)
        a *= min(1.0, p * 2.5)
        hide = int(img.height * 0.82 * (1 - e))
        if hide >= img.height:
            return
        img = img.crop((0, 0, img.width, img.height - hide))
        y += hide
    frame.alpha_composite(gfx.with_alpha(img, a), (max(0, x), max(0, y)),
                          (max(0, -x), max(0, -y)))


def _shine(img, t, ts, dur):
    """Diagonal specular sweep across an element (masked by its alpha)."""
    p = (t - ts) / dur
    if not 0 <= p <= 1:
        return img
    w, h = img.size
    xx = np.arange(w)[None, :] + np.arange(h)[:, None] * 0.6
    pos = -0.2 * w + p * 1.6 * w
    band = np.exp(-((xx - pos) / (0.06 * w)) ** 2)
    arr = np.asarray(img, np.float32).copy()
    arr[..., :3] += (255 - arr[..., :3]) * (0.75 * band)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def render_frame(i):
    """Render frame i as raw RGB bytes."""
    t = i / FPS
    st = _STATE
    frame = Image.fromarray(_background(t)).convert("RGBA")
    fa = gfx.ease_in_out_sine((t - 0.2) / 1.0) * 0.55
    if fa > 0:
        frame.alpha_composite(gfx.with_alpha(st["frame"], fa))
    for el in st["els"]:
        _place(frame, el, t)
    # Global fade-in from black on the first 0.4 s.
    if t < 0.4:
        frame = Image.blend(Image.new("RGBA", frame.size, (0, 0, 0, 255)), frame, t / 0.4)
    return frame.convert("RGB").tobytes()


def _render_chunk(args):
    """Worker: render frames [a, b) into one H.264 segment."""
    a, b, W, H, variant, seed, out = args
    _init(W, H, variant, seed)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
           "-crf", "14", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries",
           "bt709", "-color_trc", "bt709", "-color_range", "tv", out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(a, b):
        pr.stdin.write(render_frame(i))
    pr.stdin.close()
    pr.wait()
    return out


def render_variant(variant, W, H, seed, workdir, workers=4):
    """Render a whole variant; returns list of segment paths in order."""
    n = int(round(variant["duration"] * FPS))
    step = (n + workers - 1) // workers
    jobs = [(k, min(n, k + step), W, H, variant, seed, str(workdir / f"seg_{k:05d}.mp4"))
            for k in range(0, n, step)]
    with Pool(workers) as pool:
        return pool.map(_render_chunk, jobs)


def still(variant, W, H, seed, t, path):
    """Render a single frame at time t to an image (for QC)."""
    _init(W, H, variant, seed)
    Image.frombytes("RGB", (W, H), render_frame(int(round(t * FPS)))).save(path)
