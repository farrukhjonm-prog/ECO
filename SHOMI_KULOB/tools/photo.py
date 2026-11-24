"""Photo/footage layer for ШОМИ КУЛОБ ads: grading, Ken Burns, transitions.

A scene may carry
    "photo": "01_SOURCE_PHOTOS/<file>"          (read-only source)
    "kb":    [[cx, cy, zoom], [cx, cy, zoom]]     camera move start -> end
             cx, cy = normalised centre in the source, zoom 1 = cover-fit
    "grade": "warm" | "skin" | "none"            colour grade
    "shade": [top, bottom, overall]               readability darkening
    "blur":  radius in design px (e.g. end-screen backdrop)
    "embers": 0..1                                spark overlay strength

The source pixels are never altered on disk; faces are only scaled/cropped
(uniformly, no distortion).  Consecutive photo scenes overlap by 2*T seconds
and cross with a zoom-punch dissolve.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
T = 0.25  # half transition length (s)


def _ease(x):
    """Smooth ease-in-out on [0, 1]."""
    x = min(1.0, max(0.0, x))
    return 0.5 - 0.5 * np.cos(np.pi * x)


def grade(img, kind):
    """Apply a gentle, natural colour grade to an RGB PIL image."""
    if kind == "none":
        return img
    a = np.asarray(img, np.float32) / 255
    if kind == "warm":
        gain, con, sat = np.array([1.06, 1.0, 0.90]), 1.10, 1.12
    else:  # "skin": very light touch to keep skin tones true
        gain, con, sat = np.array([1.025, 1.0, 0.975]), 1.04, 1.04
    a = a * gain
    a = 0.5 + (a - 0.5) * con
    luma = (a * np.array([0.2126, 0.7152, 0.0722])).sum(-1, keepdims=True)
    a = luma + (a - luma) * sat
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


class PhotoTrack:
    """All photo scenes of one variant, prepared for per-frame sampling."""

    def __init__(self, variant, W, H):
        self.W, self.H, s = W, H, W / 1080
        self.scenes = []
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
        r = np.sqrt((xx - 0.5) ** 2 + ((yy - 0.5) * 1.1) ** 2)
        self.vig = (1 - 0.45 * np.clip(r / 0.8, 0, 1) ** 2.4)[..., None]
        for sc in variant["scenes"]:
            if "photo" not in sc:
                continue
            src = Image.open(ROOT / sc["photo"]).convert("RGB")
            # Pre-scale so the cover fit at max zoom is ~1.15x oversampled.
            zmax = max(k[2] for k in sc.get("kb", [[.5, .5, 1], [.5, .5, 1]]))
            cover = max(W / src.width, H / src.height) * zmax * 1.15
            if cover < 1:
                src = src.resize((int(src.width * cover), int(src.height * cover)),
                                 Image.LANCZOS)
            src = grade(src, sc.get("grade", "warm"))
            if sc.get("blur"):
                src = src.filter(ImageFilter.GaussianBlur(sc["blur"] * s * src.width / W))
            top, bot, overall = sc.get("shade", [0.5, 0.6, 1.0])
            shade = (overall * (1 - top * np.clip(1 - yy / 0.30, 0, 1) ** 1.6)
                     * (1 - bot * np.clip((yy - 0.50) / 0.50, 0, 1) ** 1.4))
            self.scenes.append(dict(sc=sc, src=src, shade=shade[..., None]))
        self.first = self.scenes[0]["sc"]["start"] if self.scenes else None
        self.last = self.scenes[-1]["sc"]["end"] if self.scenes else None

    def active(self, t):
        """True when photos cover time t."""
        return bool(self.scenes) and self.first <= t < self.last + 1e-6

    def _sample(self, item, t, extra_zoom):
        """Render one scene's photo at time t as a float RGB array."""
        sc, src = item["sc"], item["src"]
        p = _ease((t - sc["start"]) / (sc["end"] - sc["start"]))
        k0, k1 = sc.get("kb", [[.5, .5, 1], [.5, .5, 1]])
        cx, cy, z = [a + (b - a) * p for a, b in zip(k0, k1)]
        z *= extra_zoom
        sw, sh = src.size
        cover = max(self.W / sw, self.H / sh) * z
        cw, ch = self.W / cover, self.H / cover
        x0 = min(max(cx * sw - cw / 2, 0), sw - cw)
        y0 = min(max(cy * sh - ch / 2, 0), sh - ch)
        im = src.resize((self.W, self.H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
        return np.asarray(im, np.float32) * item["shade"]

    def frame(self, t):
        """Composite photo layer at time t (float array, full res)."""
        cur = [it for it in self.scenes
               if it["sc"]["start"] - T <= t < it["sc"]["end"] + T]
        cur = [it for it in cur if self.first <= t]
        if len(cur) == 1:
            out = self._sample(cur[0], t, 1.0)
        else:
            a, b = cur[0], cur[1]
            e = _ease((t - (b["sc"]["start"] - T)) / (2 * T))
            out = (self._sample(a, t, 1 + 0.08 * e) * (1 - e)
                   + self._sample(b, t, 1 + 0.10 * (1 - e)) * e)
        return out * self.vig

    def ember_gain(self, t):
        """Spark-overlay strength of the scene at time t."""
        for it in self.scenes:
            if it["sc"]["start"] <= t < it["sc"]["end"]:
                return it["sc"].get("embers", 0.4)
        return 0.4
