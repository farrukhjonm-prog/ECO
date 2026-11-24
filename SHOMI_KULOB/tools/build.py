"""Build pipeline for ШОМИ КУЛОБ daily ads.

    python3 tools/build.py 06_PROJECTS/<project>/project.json [--preview]

Steps: scan source folders -> music -> render 4K master per variant ->
mux + loudness master (-14 LUFS, -1.5 dBTP) -> 1080x1920 Instagram file ->
SRT subtitles + caption -> QC (ffprobe, loudness, contact sheet).
Source folders 01..05 are only ever read, never modified.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import music  # noqa: E402
import render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = {"photos": "01_SOURCE_PHOTOS", "videos": "02_SOURCE_VIDEOS", "logo": "03_LOGO",
       "menu": "04_MENU", "audio": "05_AUDIO"}
OUT = {"Reels": "07_READY_REELS", "Story": "08_READY_STORIES"}


def scan():
    """Inventory the source folders (read-only) and return a dict of lists."""
    inv = {}
    for k, d in SRC.items():
        inv[k] = sorted(str(p.relative_to(ROOT)) for p in (ROOT / d).rglob("*")
                        if p.is_file() and p.name != ".gitkeep")
    return inv


def sh(*cmd):
    """Run a command, raise on failure, return stdout+stderr text."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    return r.stdout + r.stderr


def srt(variant):
    """SRT subtitle text from the kinetic-text scenes of a variant."""
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    out, n = [], 1
    for sc in variant["scenes"]:
        if sc["type"] == "lines":
            txt = "\n".join(" ".join(r[0] for r in line) for line in sc["lines"])
        elif sc["type"] == "dish":
            p = sc["price"]
            txt = " ".join(sc["name"]) + f"\n{p['portion']} — {p['amount']} {p['currency']}"
        elif sc["type"] == "end":
            txt = "ШОМИ КУЛОБ — ҲАМИН ҲОЛО ФАРМОИШ ДИҲЕД!\n+992 934 41 41 41 · @shomi_kulob_restourant"
        else:
            continue
        out.append(f"{n}\n{ts(sc['start'])} --> {ts(sc['end'])}\n{txt}\n")
        n += 1
    return "\n".join(out)


def build(project_path, preview=False):
    """Render every variant of a project and save deliverables."""
    proj = json.loads(Path(project_path).read_text(encoding="utf-8"))
    pdir = Path(project_path).parent
    day = proj.get("date", date.today().isoformat())
    name = proj["name"]
    inv = scan()
    (pdir / "source_inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    W, H = (1080, 1920) if preview else tuple(proj.get("master", [2160, 3840]))
    tag = "4K" if H >= 3840 else f"{H}p"
    report = [f"# QC report — {day} {name}", ""]
    for vname, var in proj["variants"].items():
        if var.get("same_as"):
            # Identical cut (layout is safe for both Reels and Stories): copy files.
            src = proj["variants"][var["same_as"]]
            for suf in ("", f"_MASTER_{tag}"):
                a = ROOT / OUT[var["same_as"]] / f"{day}_{name}_{var['same_as']}{suf}.mp4"
                if a.exists():
                    shutil.copyfile(a, ROOT / OUT[vname] / f"{day}_{name}_{vname}{suf}.mp4")
            (ROOT / OUT[vname] / f"{day}_{name}_{vname}.srt").write_text(srt(src), encoding="utf-8")
            report.append(f"## {vname}: identical copy of {var['same_as']}\n")
            continue
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cuts = [sc["start"] for sc in var["scenes"]
                    if sc["type"] not in ("brandbug", "strip") and sc["start"] > 0]
            end = next(sc["start"] for sc in var["scenes"] if sc["type"] == "end")
            wav = td / "music.wav"
            music.render_music(wav, var["duration"], cuts, end, seed=proj["seed"],
                               style=proj["style"], bpm=proj.get("bpm", 120))
            segs = render.render_variant(var, W, H, proj["seed"], td)
            lst = td / "list.txt"
            lst.write_text("".join(f"file '{p}'\n" for p in segs))
            vid = td / "video.mp4"
            sh("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(vid))
            out_dir = ROOT / OUT[vname]
            base = f"{day}_{name}_{vname}"
            master = out_dir / f"{base}_MASTER_{tag}.mp4" if not preview else td / "m.mp4"
            insta = out_dir / f"{base}.mp4" if not preview else pdir / f"PREVIEW_{base}.mp4"
            af = ("loudnorm=I=-14:TP=-2:LRA=9,aresample=48000,"
                  "alimiter=limit=0.72:attack=2:release=60:level=false")
            if not preview:
                sh("ffmpeg", "-y", "-i", str(vid), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                   "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "24M",
                   "-bufsize", "48M", "-profile:v", "high", "-pix_fmt", "yuv420p",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-af", af, "-c:a", "aac", "-b:a", "320k", "-shortest",
                   "-movflags", "+faststart", str(master))
            sh("ffmpeg", "-y", "-i", str(vid), "-i", str(wav), "-map", "0:v", "-map", "1:a",
               "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264", "-preset", "slow",
               "-crf", "17", "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high",
               "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-af", af, "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
               "-shortest", "-movflags", "+faststart", str(insta))
            (out_dir / f"{base}.srt").write_text(srt(var), encoding="utf-8")
            report += qc(insta, var, pdir / f"QC_{base}.jpg")
            if not preview:
                report += qc(master, var, None)
    if proj.get("caption"):
        (ROOT / OUT["Reels"] / f"{day}_{name}_Caption.txt").write_text(proj["caption"],
                                                                         encoding="utf-8")
    (pdir / "QC_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


def qc(path, var, sheet):
    """Probe a rendered file; check format, duration, loudness; contact sheet."""
    pr = json.loads(sh("ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                       "-show_format", str(path)))
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    a = next(s for s in pr["streams"] if s["codec_type"] == "audio")
    dur = float(pr["format"]["duration"])
    loud = sh("ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-")
    summ = loud[loud.rfind("Summary:"):]
    lufs = summ.split("I:")[1].split("LUFS")[0].strip()
    peak = summ.split("Peak:")[1].split("dBFS")[0].strip()
    ok = (v["codec_name"] == "h264" and a["codec_name"] == "aac"
          and abs(dur - var["duration"]) < 0.15 and float(peak) <= -1.0)
    lines = [f"## {path.name}", f"- video: {v['codec_name']} {v['width']}x{v['height']} "
             f"{v['r_frame_rate']} {v.get('pix_fmt')} color={v.get('color_space')}",
             f"- audio: {a['codec_name']} {a['sample_rate']} Hz {a['channels']}ch",
             f"- duration: {dur:.2f}s (target {var['duration']}s)",
             f"- loudness: {lufs} LUFS integrated, true peak {peak} dBFS",
             f"- size: {int(pr['format']['size']) / 1e6:.1f} MB",
             f"- RESULT: {'PASS' if ok else 'CHECK'}", ""]
    if sheet:
        times = sorted({0.6} | {min(var['duration'] - 0.2, sc['start'] + 1.2)
                                for sc in var['scenes']} | {var['duration'] - 0.3})
        thumbs = []
        for t in times:
            tmp = Path(tempfile.mktemp(suffix=".png"))
            sh("ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
               "-vf", "scale=360:640", str(tmp))
            thumbs.append(Image.open(tmp).convert("RGB"))
        cs = Image.new("RGB", (360 * len(thumbs), 640))
        for i, im in enumerate(thumbs):
            cs.paste(im, (i * 360, 0))
        cs.save(sheet, quality=90)
    return lines


if __name__ == "__main__":
    build(sys.argv[1], preview="--preview" in sys.argv)
