"""Original procedural background music + sound design for ШОМИ КУЛОБ ads.

Everything here is synthesized from scratch with numpy (no samples, no
third-party recordings), so the result is 100% original and free for
commercial use.  The track is beat-locked: scene cuts passed in `cuts`
receive a whoosh, the end-screen start receives a riser + impact, so the
picture edit and the music always line up.

Usage (library):  render_music(path, duration, cuts, end_start, seed, style)
"""
import wave

import numpy as np

SR = 48000

# Chord progressions (MIDI root notes + minor/major flag) per style.
PROGRESSIONS = {
    "dark_luxury": [(57, "m"), (53, "M"), (48, "M"), (55, "M")],   # Am F C G
    "warm_groove": [(50, "m"), (58, "M"), (53, "M"), (57, "m")],   # Dm Bb F Am
    "bright_pop": [(48, "M"), (55, "M"), (57, "m"), (53, "M")],    # C G Am F
}


def _midi(n):
    """Return frequency in Hz for a MIDI note number."""
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n, a, r):
    """Linear attack / exponential release envelope of length n samples."""
    e = np.ones(n)
    ai = max(1, int(a * SR))
    e[:ai] = np.linspace(0, 1, ai)
    e *= np.exp(-np.arange(n) / (r * SR))
    return e


def _lowpass(x, cutoff):
    """Simple one-pole low-pass filter (vectorised via cumulative trick)."""
    alpha = 1 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    # Process in blocks for speed while staying exact.
    for i in range(0, len(x), 4096):
        blk = x[i:i + 4096]
        out = np.empty_like(blk)
        for j, v in enumerate(blk):
            acc += alpha * (v - acc)
            out[j] = acc
        y[i:i + 4096] = out
    return y


def _kick(rng):
    """Punchy synthesized kick drum."""
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7.5) * 0.95


def _clap(rng):
    """Layered noise clap."""
    n = int(0.25 * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    env = np.zeros(n)
    for d in (0.0, 0.011, 0.022):
        k = int(d * SR)
        env[k:] += np.exp(-(t[: n - k]) * 38)
    band = noise - np.concatenate([[0], noise[:-1]])
    return band * env * 0.22


def _hat(rng, open_=False):
    """Bright high-hat from differentiated noise."""
    n = int((0.18 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    hp = np.diff(np.diff(noise, prepend=0), prepend=0)
    return hp * np.exp(-t * (18 if open_ else 70)) * 0.05


def _add(buf, sig, start):
    """Mix `sig` into stereo/mono `buf` at sample index `start`."""
    s = int(start)
    if s >= len(buf) or s + len(sig) <= 0:
        return
    e = min(len(buf), s + len(sig))
    buf[s:e] += sig[: e - s]


def _whoosh(rng, dur=0.6):
    """Filtered noise sweep used on cuts (rises then falls)."""
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    env = np.sin(np.pi * t) ** 2
    sweep = _lowpass(noise, 1200) * 0.6 + np.diff(noise, prepend=0) * 0.15
    return sweep * env * 0.35


def _riser(rng, dur):
    """Noise + pitch riser leading into the end screen."""
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    f = 200 + 1800 * t ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.05
    noise = np.diff(rng.standard_normal(n), prepend=0) * 0.10
    return (tone + noise) * t ** 2


def _impact(rng):
    """Deep cinematic hit + sub drop."""
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    sub = np.sin(2 * np.pi * np.cumsum(60 * np.exp(-t * 1.5) + 30) / SR)
    noise = _lowpass(rng.standard_normal(n), 900)
    return sub * np.exp(-t * 2.2) * 0.9 + noise * np.exp(-t * 5) * 0.5


def render_music(path, duration, cuts, end_start, seed=1, style="dark_luxury",
                 bpm=120):
    """Write a stereo 48 kHz WAV of `duration` seconds to `path`.

    cuts      -- list of scene-cut times (s) that get a whoosh
    end_start -- time the end screen starts (riser before, impact on it)
    """
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    beat = 60.0 / bpm
    prog = PROGRESSIONS.get(style, PROGRESSIONS["dark_luxury"])
    bar = beat * 4
    kick, clap = _kick(rng), _clap(rng)

    # Pads + bass: one chord per bar.
    t_all = np.arange(n) / SR
    for b in range(int(np.ceil(duration / bar))):
        root, q = prog[b % len(prog)]
        third = 3 if q == "m" else 4
        s, e = int(b * bar * SR), min(n, int((b + 1) * bar * SR))
        if s >= n:
            break
        tt = t_all[s:e] - b * bar
        seg = np.zeros(e - s)
        for k, iv in enumerate((0, third, 7, 12)):
            f = _midi(root + iv)
            for det in (-0.08, 0.08):
                ph = 2 * np.pi * f * (1 + det / 100) * tt
                seg += (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.018
        fade = np.minimum(1, np.minimum(tt / 0.25, (bar - tt) / 0.25))
        pad = seg * fade
        L[s:e] += pad
        R[s:e] += np.roll(pad, 240)
        # Sub bass on 8ths with soft pluck envelope.
        fb = _midi(root - 12)
        for k in range(8):
            bs = int((b * bar + k * beat / 2) * SR)
            ln = int(beat / 2 * SR)
            tb = np.arange(ln) / SR
            sig = np.sin(2 * np.pi * fb * tb) * np.exp(-tb * 6) * 0.22
            _add(L, sig, bs)
            _add(R, sig, bs)

    L = _lowpass(L, 2600)
    R = _lowpass(R, 2600)

    # Drums.  Drop drums for the first bar (intro) for a cinematic build.
    for i in range(int(duration / beat) + 1):
        tb = i * beat
        if tb >= duration:
            break
        intro = tb < bar * 0.75
        if not intro and not (end_start - beat * 2 <= tb < end_start):
            _add(L, kick, tb * SR)
            _add(R, kick, tb * SR)
            if i % 2 == 1:
                c = clap
                _add(L, c, tb * SR + 60)
                _add(R, c, tb * SR)
        for h in (0, 0.5):
            hs = (tb + h * beat) * SR
            hat = _hat(rng, open_=(h == 0.5 and i % 4 == 3))
            pan = 0.7 if h else 0.4
            _add(L, hat * pan, hs)
            _add(R, hat * (1 - pan + 0.3), hs)

    # Sound design.
    for c in cuts:
        w = _whoosh(rng)
        _add(L, w, (c - 0.3) * SR)
        _add(R, np.roll(w, 300), (c - 0.3) * SR)
    rz = _riser(rng, 1.5)
    _add(L, rz, (end_start - 1.5) * SR)
    _add(R, rz, (end_start - 1.5) * SR)
    imp = _impact(rng)
    _add(L, imp, end_start * SR)
    _add(R, imp, end_start * SR)

    # Fade-out last 1.2 s, soft-clip, write.
    fo = int(1.2 * SR)
    ramp = np.linspace(1, 0, fo) ** 1.5
    L[-fo:] *= ramp
    R[-fo:] *= ramp
    st = np.stack([L, R], axis=1)
    st = np.tanh(st * 1.4) / 1.4
    st /= max(1e-9, np.abs(st).max()) / 0.89
    pcm = (st * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path
