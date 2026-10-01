"""Generate real playable vertical MP4 development media for FarmBuzz Shorts.

The FarmBuzz Shorts player is an immersive vertical video viewer, but the
existing seed only ever pointed Shorts at still JPEGs, so no Short was ever
actually a video. This module renders genuinely playable, theme-specific
vertical clips (H.264 / yuv420p / faststart) plus JPEG poster thumbnails and
stores them inside the existing FarmBuzz media storage so they are served by
the normal ``/api/v1/farmbuzz/media/...`` endpoint.

Design notes:
- Frames are rendered with Pillow and piped as raw RGB straight into ffmpeg
  (libx264). No intermediate frame files are written to disk.
- Text is kept inside the upper 45% of the frame: the Shorts player overlays
  the author, title, category and action rail on the lower/right side.
- Every clip is deterministic (``seed = index``) so re-runs reproduce the same
  asset, and existing valid files are skipped unless ``force=True``.
- Audio is a very quiet filtered pink-noise ambience so the player's mute
  control is meaningful.

Usage:
    python seed_farmbuzz_video.py --count 120
    python seed_farmbuzz_video.py --count 120 --force --workers 8
"""
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

W, H = 540, 960
FPS = 24
SECONDS = 5
FRAMES = FPS * SECONDS
JPEG_QUALITY = 82

# (deep, mid, accent, soil) - every clip gets a distinct palette.
PALETTES = [
    ("#0F2E1E", "#2D8659", "#E9B640", "#3B2A18"),
    ("#0B3D2E", "#52B788", "#D8F3DC", "#2E2013"),
    ("#14304F", "#3E7CB1", "#FFD166", "#1E2A38"),
    ("#2A1B3D", "#7C5CD6", "#F4A261", "#241A2E"),
    ("#3D2409", "#D97706", "#FDE68A", "#2A1B0A"),
    ("#40161C", "#B23A48", "#E9B640", "#2B1014"),
    ("#12281A", "#40916C", "#95D5B2", "#33261A"),
    ("#0E2F2B", "#2A9D8F", "#E8F5F2", "#1C2A24"),
    ("#1B2A12", "#6A994E", "#DDA15E", "#2C2312"),
    ("#102A43", "#4C8BBF", "#9BD1A4", "#22303C"),
    ("#33200B", "#A4703A", "#EBC49A", "#241810"),
    ("#1A3325", "#74C69D", "#E9F5EF", "#2A2118"),
]

# Category keyword -> scene renderer.
SCENES = [
    ("irrigation", "irrigation"),
    ("drip", "irrigation"),
    ("market", "market"),
    ("enam", "market"),
    ("mandi", "market"),
    ("machinery", "machinery"),
    ("tractor", "machinery"),
    ("sprayer", "machinery"),
    ("zerotill", "machinery"),
    ("orchard", "orchard"),
    ("mango", "orchard"),
    ("banana", "orchard"),
    ("organic", "orchard"),
    ("greenmanure", "orchard"),
    ("jeevamrit", "orchard"),
    ("crop", "field"),
    ("soil", "field"),
    ("paddy", "field"),
    ("rice", "field"),
    ("cotton", "field"),
    ("chilli", "field"),
    ("maize", "field"),
    ("groundnut", "field"),
    ("tomato", "field"),
    ("onion", "field"),
    ("wheat", "field"),
    ("sugarcane", "field"),
]

_FONT_CACHE = {}
_FONT_CANDIDATES_BOLD = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
)
_FONT_CANDIDATES_REG = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
)


def ffmpeg_bin():
    """Locate ffmpeg: bundled imageio-ffmpeg copy first, then PATH."""
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    for cand in ("ffmpeg", "ffmpeg.exe"):
        try:
            out = subprocess.run(
                [cand, "-version"], capture_output=True, timeout=15)
            if out.returncode == 0:
                return cand
        except Exception:
            continue
    raise RuntimeError(
        "ffmpeg not found. Install it with: pip install imageio-ffmpeg")


def font(size, bold=True):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    paths = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REG
    f = None
    for p in paths:
        if os.path.isfile(p):
            try:
                f = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if f is None:
        f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def scene_for(category, crop, title):
    blob = " ".join(x for x in (category, crop, title) if x).lower()
    for key, scene in SCENES:
        if key in blob:
            return scene
    return "field"


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def hexrgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def dim(img, amount=0.30):
    overlay = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, overlay, amount)


def build_background(pal, scene, rnd):
    """Static vertical gradient sky + ground, rendered once per clip."""
    deep, mid, accent, soil = (hexrgb(c) for c in pal)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)

    horizon = int(H * 0.46)
    for y in range(horizon):
        t = y / max(1, horizon)
        # two-stop vertical sky gradient with a warm band near the horizon
        c = mix(deep, mid, t ** 0.85)
        if t > 0.72:
            c = mix(c, mix(mid, accent, 0.35), (t - 0.72) / 0.28 * 0.55)
        d.line([(0, y), (W, y)], fill=c)

    # sun / moon glow
    sun_x = int(W * (0.22 + 0.56 * rnd.random()))
    sun_y = int(horizon * (0.30 + 0.30 * rnd.random()))
    for r, a in ((190, 0.05), (130, 0.07), (78, 0.10), (44, 0.22)):
        d.ellipse([sun_x - r, sun_y - r, sun_x + r, sun_y + r],
                  fill=mix(deep, accent, a * 3.0))
    d.ellipse([sun_x - 26, sun_y - 26, sun_x + 26, sun_y + 26], fill=accent)

    # distant hills
    hills = mix(deep, mid, 0.55)
    for k, (amp, yb, col) in enumerate((
            (0.055, 0.06, mix(deep, mid, 0.40)),
            (0.040, 0.11, hills))):
        pts = [(0, horizon)]
        for x in range(0, W + 12, 12):
            ph = x / W * (2.4 + k)
            y = horizon - int(H * (yb + amp * (0.5 + 0.5 * float(
                (0.5 + 0.5 * _sin(ph + k * 1.7)))) ))
            pts.append((x, y))
        pts.append((W, horizon))
        d.polygon(pts, fill=col)

    # ground
    for y in range(horizon, H):
        t = (y - horizon) / max(1, H - horizon)
        d.line([(0, y), (W, y)], fill=mix(soil, (0, 0, 0), t * 0.30))
    return img, horizon, (deep, mid, accent, soil)


def _sin(x):
    import math
    return math.sin(x)


# --------------------------------------------------------------------------
# scene painters: (img, d, t, ctx) with t in [0,1)
# --------------------------------------------------------------------------

def paint_field(img, d, t, ctx):
    deep, mid, accent, soil = ctx["cols"]
    horizon = ctx["horizon"]
    rnd = ctx["rnd"]
    plants = ctx["plants"]

    # furrows with slow scroll to read as motion
    scroll = (t * 34) % 26
    for i in range(-1, 15):
        y = horizon + 16 + i * 26 + scroll
        if y > H:
            break
        d.line([(0, y), (W, y + 26)],
               fill=mix(soil, mid, 0.16 - i * 0.004), width=3)

    for px, py, ph, col, sc in plants:
        sway = _sin(t * 6.28318 * 1.0 + px * 0.05) * (5 + sc * 4)
        base_x, base_y = px, py
        tip_x = base_x + sway
        tip_y = base_y - ph
        d.line([(base_x, base_y), (tip_x, tip_y)], fill=col, width=max(1, int(3 * sc)))
        for f in range(3):
            ft = 0.30 + f * 0.26
            lx = base_x + (tip_x - base_x) * ft
            ly = base_y + (tip_y - base_y) * ft
            lw = int(15 * sc * (1 - f * 0.16))
            side = 1 if f % 2 == 0 else -1
            d.ellipse([lx - lw, ly - int(lw * 0.42), lx + lw * 0.3, ly + int(lw * 0.30)],
                      fill=mix(col, accent, 0.22))
            d.line([(lx, ly), (lx + side * lw, ly - int(lw * 0.5))],
                   fill=mix(col, accent, 0.22), width=max(1, int(2 * sc)))
        r = max(2, int(4 * sc))
        d.ellipse([tip_x - r, tip_y - r, tip_x + r, tip_y + r], fill=accent)


def paint_irrigation(img, d, t, ctx):
    deep, mid, accent, soil = ctx["cols"]
    horizon = ctx["horizon"]
    rnd = ctx["rnd"]

    # canal band
    band_top = horizon + 40
    for y in range(band_top, band_top + 150):
        tt = (y - band_top) / 150.0
        d.line([(0, y), (W, y)],
               fill=mix(mix(deep, accent, 0.42), deep, tt * 0.5))
    for i in range(0, 9):
        yy = band_top + 12 + i * 16 + (t * 26) % 16
        d.line([(0, yy), (W, yy)], fill=mix(accent, (255, 255, 255), 0.55), width=2)

    # pipes
    pipe_y = horizon - 30
    d.rounded_rectangle([-10, pipe_y, W + 10, pipe_y + 26], 8,
                        fill=mix(mid, (0, 0, 0), 0.25))
    for i in range(6):
        x = 40 + i * 88
        d.ellipse([x - 9, pipe_y + 20, x + 9, pipe_y + 38],
                  fill=mix(accent, (255, 255, 255), 0.30))
        d.rectangle([x - 2, pipe_y + 34, x + 2, pipe_y + 60],
                    fill=mix(mid, accent, 0.45))

    # falling droplets
    for i in range(46):
        x0 = 40 + (i % 6) * 88
        ph = (i * 0.137) % 1.0
        y = pipe_y + 60 + ((ph + t * 1.15) % 1.0) * (H - pipe_y - 90)
        ln = 12 + (i % 4) * 5
        d.line([(x0, y), (x0, y + ln)],
               fill=mix(accent, (255, 255, 255), 0.72), width=3)
        d.ellipse([x0 - 3, y + ln - 3, x0 + 3, y + ln + 3],
                  fill=mix(accent, (255, 255, 255), 0.85))

    # wet soil rows
    for i in range(-1, 12):
        y = band_top + 170 + i * 30
        if y > H:
            break
        d.line([(0, y), (W, y + 22)], fill=mix(soil, accent, 0.14), width=4)


def paint_market(img, d, t, ctx):
    deep, mid, accent, soil = ctx["cols"]
    horizon = ctx["horizon"]
    bars = ctx["bars"]
    base = int(H * 0.72)

    d.rectangle([0, horizon + 30, W, H], fill=mix(soil, deep, 0.35))
    d.line([(0, base), (W, base)], fill=mix(accent, (255, 255, 255), 0.30), width=4)

    n = len(bars)
    bw = W / (n * 1.65)
    gap = (W - n * bw) / (n + 1)
    for i, base_h in enumerate(bars):
        x0 = gap + i * (bw + gap)
        grow = min(1.0, max(0.0, (t * 2.0 - i * 0.16)))
        h = base_h * grow
        col = mix(mid, accent, i / max(1, n - 1))
        d.rounded_rectangle([x0, base - h, x0 + bw, base], 6, fill=col)
        d.rectangle([x0, base - h, x0 + bw, base - h + 10],
                    fill=mix(col, (255, 255, 255), 0.40))

    # trend line
    pts = []
    for i, base_h in enumerate(bars):
        x0 = gap + i * (bw + gap) + bw / 2
        grow = min(1.0, max(0.0, (t * 2.0 - i * 0.16)))
        pts.append((x0, base - base_h * grow - 16 - _sin(t * 6.28 + i) * 3))
    if len(pts) > 1:
        d.line(pts, fill=mix(accent, (255, 255, 255), 0.65), width=4, joint="curve")
        for x, y in pts:
            d.ellipse([x - 5, y - 5, x + 5, y + 5],
                      fill=mix(accent, (255, 255, 255), 0.85))

    # rupee coin
    cx, cy = int(W * 0.80), int(horizon * 0.55)
    d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=accent)
    d.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], outline=(255, 255, 255), width=3)
    d.text((cx, cy), "\u20b9", font=font(38, True), anchor="mm",
           fill=(120, 70, 10))


def paint_machinery(img, d, t, ctx):
    deep, mid, accent, soil = ctx["cols"]
    horizon = ctx["horizon"]
    ground = horizon + 90
    d.rectangle([0, ground, W, H], fill=mix(soil, deep, 0.30))

    # furrow lines
    for i in range(7):
        y = ground + 30 + i * 40
        d.line([(0, y), (W, y + 14)], fill=mix(soil, mid, 0.12), width=3)

    # tractor body
    bx, by = int(W * 0.30), ground - 90
    d.rounded_rectangle([bx, by, bx + 190, by + 74], 10, fill=mix(mid, (0, 0, 0), 0.10))
    d.polygon([(bx + 60, by), (bx + 140, by), (bx + 150, by - 62), (bx + 78, by - 62)],
              fill=mix(mid, accent, 0.22))
    d.rectangle([bx + 88, by - 52, bx + 142, by - 16], fill=mix(deep, accent, 0.30))
    d.ellipse([bx + 158, by + 2, bx + 214, by + 58], fill=mix(accent, (0, 0, 0), 0.18))

    # exhaust puffs
    for i in range(7):
        ph = (i * 0.14 + t * 0.9) % 1.0
        r = 10 + ph * 26
        cx = bx + 40 - ph * 30
        cy = by - 12 - ph * 74
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=mix(deep, (255, 255, 255), 0.16 + 0.10 * (1 - ph)))

    # rotating wheels
    for wx, wr in ((bx + 42, 44), (bx + 186, 30)):
        ang = t * 6.28318 * 1.4
        d.ellipse([wx - wr, by + 40 - wr, wx + wr, by + 40 + wr],
                  fill=mix((28, 28, 30), mid, 0.20))
        d.ellipse([wx - wr + 7, by + 40 - wr + 7, wx + wr - 7, by + 40 + wr - 7],
                  outline=mix(accent, (0, 0, 0), 0.10), width=5)
        for s in range(6):
            a = ang + s * 6.28318 / 6
            d.line([(wx, by + 40), (wx + _sin(a) * (wr - 9), by + 40 - _sin(a + 1.57) * (wr - 9))],
                   fill=mix(accent, (0, 0, 0), 0.25), width=4)


def paint_orchard(img, d, t, ctx):
    deep, mid, accent, soil = ctx["cols"]
    horizon = ctx["horizon"]
    trees = ctx["trees"]

    for y in range(horizon + 40, H):
        tt = (y - horizon - 40) / max(1, H - horizon - 40)
        d.line([(0, y), (W, y)], fill=mix(soil, (0, 0, 0), tt * 0.25))

    for px, py, s in trees:
        sway = _sin(t * 6.28318 + px * 0.04) * (3 + s * 3)
        trunk = mix(soil, (0, 0, 0), 0.25)
        d.rectangle([px - int(7 * s), py - int(150 * s),
                     px + int(7 * s), py], fill=trunk)
        for j in range(4):
            ly = py - int(150 * s) + j * int(34 * s)
            d.line([(px, ly), (px - int(30 * s), ly - int(18 * s))],
                   fill=trunk, width=max(2, int(5 * s)))
            d.line([(px, ly), (px + int(30 * s), ly - int(18 * s))],
                   fill=trunk, width=max(2, int(5 * s)))
        for j in range(3):
            r = int(66 * s)
            ox = sway * (1 - j * 0.25)
            cx = px + ox - int(38 * s) + j * int(38 * s)
            cy = py - int(168 * s) - j * int(30 * s)
            d.ellipse([cx - r, cy - r * 0.78, cx + r, cy + r * 0.78],
                      fill=mix(mid, deep, 0.30 + j * 0.12))
        for j in range(6):
            ph = (j * 0.17 + t * 0.55) % 1.0
            fx = px + sway + _sin(j * 2.1 + t * 3.0) * (34 * s)
            fy = py - int(168 * s) + 14 + ph * 34 * s
            r = max(3, int(7 * s))
            d.ellipse([fx - r, fy - r, fx + r, fy + r], fill=accent)

    # drifting leaves
    for j in range(12):
        ph = (j * 0.083 + t * 0.30) % 1.0
        lx = (j * 71 + t * 46) % (W + 60) - 30
        ly = H * 0.42 + ph * (H * 0.52)
        r = 7 + (j % 3) * 4
        d.ellipse([lx - r, ly - r * 0.45, lx + r, ly + r * 0.45],
                  fill=mix(mid, accent, 0.35))


PAINTERS = {
    "field": paint_field,
    "irrigation": paint_irrigation,
    "market": paint_market,
    "machinery": paint_machinery,
    "orchard": paint_orchard,
}


def make_clip(index, title, category, crop, out_dir, force=False):
    """Render one vertical MP4 + JPEG poster. Returns (mp4_path, jpg_path, bytes)."""
    import math
    import random as _random

    stem = f"short_{index + 1:04d}"
    mp4 = os.path.join(out_dir, stem + ".mp4")
    jpg = os.path.join(out_dir, stem + ".jpg")
    ok_mp4 = os.path.isfile(mp4) and os.path.getsize(mp4) > 4096
    ok_jpg = os.path.isfile(jpg) and os.path.getsize(jpg) > 900
    if ok_mp4 and ok_jpg and not force:
        return mp4, jpg, os.path.getsize(mp4)

    os.makedirs(out_dir, exist_ok=True)
    rnd = _random.Random(90210 + index)
    pal = PALETTES[index % len(PALETTES)]
    scene = scene_for(category, crop, title)
    base, horizon, cols = build_background(pal, scene, rnd)

    # scene props
    plants, trees, bars = [], [], []
    for i in range(26):
        depth = i / 25.0
        py = horizon + 26 + depth * (H - horizon) * 0.95
        sc = 0.35 + depth * 1.25
        plants.append((
            int(W * (0.04 + 0.92 * rnd.random())),
            int(py),
            int((46 + rnd.random() * 40) * sc),
            mix(cols[1], cols[0], 0.30 + rnd.random() * 0.35),
            sc))
    for i in range(7):
        depth = 0.25 + (i / 6.0) * 0.75
        trees.append((
            int(W * (0.08 + 0.84 * rnd.random())),
            int(horizon + 30 + depth * (H - horizon) * 0.80),
            0.40 + depth * 0.85))
    for i in range(7):
        bars.append(90 + rnd.random() * 200)

    ctx = {"rnd": rnd, "horizon": horizon, "cols": cols,
           "plants": plants, "trees": trees, "bars": bars}

    # ---- text layout (upper area only; player overlays the rest) ----
    badge = (category or "FarmBuzz").strip()[:26]
    main = (title or crop or "Agri Short").strip()[:70]
    fb, fr = font(23, True), font(37, True)
    tmp = Image.new("RGB", (10, 10))
    dtmp = ImageDraw.Draw(tmp)
    main_lines = wrap(dtmp, main, fb, W - 96)[:3]
    del fr  # title uses the smaller bold face; kept layout in one place

    proc = subprocess.Popen(
        [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-",
         "-f", "lavfi", "-i",
         f"anoisesrc=c=pink:r=44100:a=0.045:d={SECONDS},lowpass=f=700",
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
         "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-level", "3.1",
         "-g", str(FPS * 2), "-movflags", "+faststart",
         "-c:a", "aac", "-b:a", "48k", "-ar", "44100", "-ac", "1",
         mp4],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE)

    poster_saved = False
    try:
        for fi in range(FRAMES):
            t = fi / float(FRAMES)
            frame = base.copy()
            d = ImageDraw.Draw(frame)
            PAINTERS[scene](frame, d, t, ctx)
            d = ImageDraw.Draw(frame)
            # soft top scrim behind the badge/title
            scrim = Image.new("L", (1, 150), 0)
            sd = ImageDraw.Draw(scrim)
            for y in range(150):
                sd.point((0, y), fill=int(150 * (1 - y / 150.0) ** 1.4))
            scrim = scrim.resize((W, 150))
            dark = Image.new("RGB", (W, 150), (0, 0, 0))
            frame.paste(dark, (0, 0), scrim)
            d = ImageDraw.Draw(frame)

            fade = min(1.0, max(0.0, (t - 0.10) / 0.16))
            rise = int((1 - fade) * 16)

            # category badge
            bw = int(d.textlength(badge, font=fb)) + 34
            bx0, by0 = 48, 74 + rise
            d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + 38], 19,
                                fill=mix(cols[2], (0, 0, 0), 0.18))
            d.text((bx0 + 17, by0 + 19), badge, font=fb, anchor="lm",
                   fill=(24, 20, 8))

            # title lines
            y = by0 + 74
            for ln in main_lines:
                alpha_t = min(1.0, max(0.0, (t - 0.18) / 0.18))
                if alpha_t <= 0:
                    y += 46
                    continue
                shadow = Image.new("RGB", (W, 60), (0, 0, 0))
                d.text((50, y + 3), ln, font=fb, fill=(0, 0, 0))
                d.text((48, y), ln, font=fb, fill=(255, 255, 255))
                y += 46

            if crop:
                d.text((50, y + 10), "\u2022  " + str(crop)[:28],
                       font=font(19, False), fill=(238, 244, 238))

            # progress bar
            pw = int(W * 0.5)
            d.rounded_rectangle([40, H - 118, 40 + pw, H - 113], 3,
                                fill=(255, 255, 255))
            d.rounded_rectangle([40, H - 118, 40 + int(pw * t), H - 113], 3,
                                fill=cols[2])

            if not poster_saved and fi >= int(FRAMES * 0.45):
                frame.save(jpg, "JPEG", quality=JPEG_QUALITY, optimize=True)
                poster_saved = True

            proc.stdin.write(frame.tobytes())
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
    err = proc.stderr.read().decode("utf-8", "replace")
    rc = proc.wait()
    if rc != 0 or not os.path.isfile(mp4) or os.path.getsize(mp4) < 4096:
        raise RuntimeError(f"ffmpeg failed for {stem}: {err.strip()[:400]}")
    if not poster_saved or not os.path.isfile(jpg):
        with Image.open(base) as f:
            f.save(jpg, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return mp4, jpg, os.path.getsize(mp4)


def _job(a):
    try:
        mp4, jpg, size = make_clip(*a)
        return (a[0], os.path.basename(mp4), os.path.basename(jpg), size, None)
    except Exception as e:  # noqa: BLE001
        return (a[0], None, None, 0, str(e)[:300])


def generate(index, title, category, crop, out_dir, force=False):
    return _job((index, title, category, crop, out_dir, force))


def main():
    import argparse
    from app.config import settings

    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=120)
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    args = ap.parse_args()

    from seed_farmbuzz import TOPICS

    out_dir = args.out or os.path.join(
        settings.STORAGE_LOCAL_PATH, "farmbuzz", "seed", "video")
    os.makedirs(out_dir, exist_ok=True)

    topics = (TOPICS * ((args.count // len(TOPICS)) + 2))[:args.count]
    jobs = []
    for i, (cat, crop, title, _cap, _tags) in enumerate(topics):
        jobs.append((i, title, cat, crop, out_dir, args.force))

    print(f"ffmpeg: {ffmpeg_bin()}")
    print(f"Generating {len(jobs)} vertical clips -> {out_dir}")
    done = failed = 0
    total_bytes = 0
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for idx, m, j, size, err in ex.map(_job, jobs, chunksize=2):
                done += 1
                if err:
                    failed += 1
                    print(f"  [{idx + 1}] FAILED: {err}")
                else:
                    total_bytes += size
                    if done % 20 == 0 or done == len(jobs):
                        print(f"  {done}/{len(jobs)} clips "
                              f"({total_bytes / 1048576:.1f} MB)")
    else:
        for j in jobs:
            idx, m, jp, size, err = _job(j)
            done += 1
            if err:
                failed += 1
                print(f"  [{idx + 1}] FAILED: {err}")
            else:
                total_bytes += size
                if done % 20 == 0 or done == len(jobs):
                    print(f"  {done}/{len(jobs)} clips "
                          f"({total_bytes / 1048576:.1f} MB)")

    vids = [f for f in os.listdir(out_dir) if f.endswith(".mp4")]
    thumbs = [f for f in os.listdir(out_dir) if f.endswith(".jpg")]
    print(f"Done. mp4={len(vids)} jpg={len(thumbs)} "
          f"size={total_bytes / 1048576:.1f} MB failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
