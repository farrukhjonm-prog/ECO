# ШОМИ КУЛОБ — automated ad production

Working folder and render pipeline for Instagram Reels and Stories ads.

| Folder | Purpose |
|---|---|
| `01_SOURCE_PHOTOS` | Original food photos. Read-only, never modified. |
| `02_SOURCE_VIDEOS` | Original restaurant footage. Read-only. |
| `03_LOGO` | **Official logo** (PNG/SVG, transparent if possible). |
| `04_MENU` | Menu files (photo/PDF/text) with **exact dish names and prices**. |
| `05_AUDIO` | Optional own audio (e.g. a recorded voice-over). |
| `06_PROJECTS` | One folder per video: `project.json`, QC report and contact sheets. |
| `07_READY_REELS` | Finished Reels: Instagram 1080×1920, 4K master, `.srt` subtitles, caption. |
| `08_READY_STORIES` | Finished Stories (same set). |
| `09_ARCHIVE` | Older deliverables. |
| `tools/` | Pipeline code and fonts (Montserrat and Oswald, SIL OFL). |

## Build a video

```bash
cd SHOMI_KULOB
python3 tools/build.py 06_PROJECTS/<project>/project.json            # 4K master + Instagram file
python3 tools/build.py 06_PROJECTS/<project>/project.json --preview  # fast 1080p check
```

Requirements: Python 3 with `numpy` and `Pillow`, plus `ffmpeg`.

A `project.json` describes each variant (`Reels`, `Story`) as a timed list of scenes:

- `intro`: animated wordmark
- `lines`: kinetic text; each run is `[text, colour, optional size]`, with colour `w`, `gold` or `red`
- `brandbug`: small brand name at the top
- `end`: the fixed contact screen (ШОМИ КУЛОБ, ҲАМИН ҲОЛО ФАРМОИШ ДИҲЕД!, the phone number and @shomi_kulob_restourant). It settles within 1 s and then stays still for at least 4 s.

Any scene can also take a background photo (`photo`, `kb` camera move, `grade`, `shade`, `blur`, `embers`; see `tools/photo.py`). Consecutive photo scenes cross with a beat-synced zoom dissolve. Add `"panel": true` to a `lines` scene to place a soft dark card behind the text over busy photos. Faces are only scaled and cropped, never reshaped or retouched.

Scene starts are placed on the 120 BPM beat grid (every 0.5 s). The music generator adds a whoosh on every cut and a riser and impact into the end screen.

## Output specs

- 9:16, H.264 High, yuv420p, Rec.709 tags, 30 fps, AAC 48 kHz
- Master: 2160×3840. Instagram: 1080×1920. Both have `+faststart`.
- Audio is normalised to −14 LUFS integrated with a true peak of −1.5 dBTP or lower.
- Music and sound effects are synthesized from scratch by `tools/music.py`, so they are original and free for commercial use.
- All text stays inside an 860 px-wide centre column between y≈330 and y≈1250 (1080 scale), which is safe for both the Reels and the Stories UI.

## Content rules (enforced by process)

- Dish names, prices, ingredients and portions are copied **exactly** from `04_MENU`. Nothing is shown if it can't be verified there.
- The official logo is used only from `03_LOGO`, never redrawn. Until a logo file is supplied, the brand appears as the text wordmark “ШОМИ КУЛОБ”.
- Nothing is published to Instagram without the owner's approval.

## Privacy

This GitHub repository is **public**. Source media (folders 01–05) and any video showing a real person are listed in `.gitignore` and are not pushed unless the owner approves.

## Known limitations

- **Tajik female voice-over:** no commercially licensed Tajik (tg-TJ) neural voice is reachable from this environment. Microsoft Azure/Edge, Google Cloud and Amazon Polly offer no Tajik voice. Meta MMS-TTS has Tajik, but it is licensed CC-BY-NC (non-commercial only) and is not a selectable female voice. Videos therefore run on kinetic Tajik text, which also serves as the subtitles; the `.srt` files are ready for when a voice is added. To add a voice, put a commercially cleared Tajik recording in `05_AUDIO` (for example from a native female voice artist), or provide an API key for a TTS service that supports Tajik. It can then be mixed under the music with ducking.
