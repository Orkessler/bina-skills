#!/usr/bin/env python3
"""בינה והשכל: makes a vertical WhatsApp status video (up to 15 seconds) from photos and clips.

Same result as the skill's page: photos fill the frame (wide ones over a blurred copy),
the logo on a contrasting plate at the top, the business name and an optional line at the
bottom, a closing card, and music generated here so there is nothing to license.

Usage:
  python3 make_video.py --name "דפוס השלום" [--line "מבצע חנוכה!"] [--logo logo.png]
                        [--style upbeat|calm|festive|none] [--max 15] --out out.mp4 FILE_OR_FOLDER...
Needs ffmpeg, Pillow and numpy.
"""
import argparse, math, os, shutil, subprocess, sys, tempfile, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features

W, H, FPS, END = 720, 1280, 30, 2.0
NAVY, GREEN2 = (15, 33, 64), (61, 220, 151)
HERE = Path(__file__).resolve().parent.parent
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}
VID_EXT = {".mp4", ".mov", ".m4v", ".webm", ".3gp"}


def font(bold, size):
    name = "Rubik-Bold.ttf" if bold else "Rubik-Regular.ttf"
    for p in [HERE / "assets" / "fonts" / name, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


RAQM = features.check("raqm")


def shape(text):
    """Text ready for drawing right to left, with or without Pillow's raqm."""
    if RAQM:
        return text, {"direction": "rtl"}
    try:
        from bidi.algorithm import get_display
        return get_display(text), {}
    except ImportError:
        return text[::-1], {}


def wrap(draw, text, f, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = f"{line} {w}".strip()
        if line and draw.textlength(shape(t)[0], font=f, **shape(t)[1]) > max_w:
            lines.append(line); line = w
        else:
            line = t
    lines.append(line)
    return lines[:2]


def draw_text(draw, text, f, cy, max_w, lh, fill="white"):
    lines = wrap(draw, text, f, max_w)
    top = cy - (len(lines) - 1) * lh
    for i, l in enumerate(lines):
        s, kw = shape(l)
        draw.text((W // 2, top + i * lh), s, font=f, fill=fill, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, 90), **kw)


def logo_plate(logo):
    """Light plate for dark logos, navy for light ones."""
    a = np.asarray(logo.convert("RGBA").resize((48, 48)))
    m = a[..., 3] > 128
    lum = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2])[m].mean() if m.any() else 0
    return NAVY if lum > 170 else (255, 255, 255)


def paste_logo(canvas, logo, max_w, cy):
    lw = int(min(max_w, max_w * logo.width / logo.height)); lh = int(lw * logo.height / logo.width)
    lg = logo.resize((lw, lh), Image.LANCZOS)
    p = max(14, int(lw * 0.09)); x, y = (W - lw) // 2, int(cy - lh / 2)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x - p, y - p + 6, x + lw + p, y + lh + p + 6), 22, fill=(0, 0, 0, 90))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
    ImageDraw.Draw(canvas).rounded_rectangle((x - p, y - p, x + lw + p, y + lh + p), 22, fill=logo_plate(logo) + (255,))
    canvas.alpha_composite(lg, (x, y))


def overlay_png(path, name, line, logo):
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = np.zeros((H, W, 4), np.uint8)
    y0 = int(H * 0.62)
    alpha = np.linspace(0, 0.78 * 255, H - y0).astype(np.uint8)
    grad[y0:, :, 3] = alpha[:, None]
    c.alpha_composite(Image.fromarray(grad, "RGBA"))
    d = ImageDraw.Draw(c)
    if line:
        draw_text(d, line, font(True, 40), int(H * 0.74), W - 100, 48)
    draw_text(d, name, font(True, 62), int(H * 0.835), W - 80, 70)
    if logo:
        paste_logo(c, logo, 190, int(H * 0.1 + 95))
    c.save(path)


def end_card(path, name, line, logo):
    c = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(c)
    if logo:
        paste_logo(c, logo, 380, int(H * 0.42))
    draw_text(d, name, font(True, 64), int(H * (0.62 if logo else 0.5)), W - 80, 72)
    if line:
        draw_text(d, line, font(True, 40), int(H * (0.69 if logo else 0.58)), W - 100, 48, fill=GREEN2)
    c.convert("RGB").save(path)


# ---------- music: the page's three styles, synthesized ----------
SR = 44100
STYLES = {
    "calm": dict(bpm=72, prog=[[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]),
    "upbeat": dict(bpm=112, prog=[[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]),
    "festive": dict(bpm=124, prog=[[48, 52, 55], [53, 57, 60], [55, 59, 62], [48, 52, 55]]),
}


def music(path, style, length):
    S = STYLES[style]; beat = 60 / S["bpm"]; bar = beat * 4
    n = int(SR * (length + 0.5)); out = np.zeros(n)
    rng = np.random.default_rng(7)
    f = lambda m: 440 * 2 ** ((m - 69) / 12)

    def tone(m, t, d, kind="sine", vol=0.1):
        i0 = int(t * SR); k = int(d * SR)
        if i0 >= n: return
        k = min(k, n - i0); tt = np.arange(k) / SR
        ph = 2 * np.pi * f(m) * tt
        w = np.sin(ph) if kind == "sine" else (2 / np.pi) * np.arcsin(np.sin(ph)) if kind == "tri" else np.sign(np.sin(ph)) * 0.5
        env = np.minimum(1, tt / 0.02) * np.exp(-tt / (d * 0.45))
        out[i0:i0 + k] += vol * w * env

    def hit(t, kind):
        i0 = int(t * SR)
        if i0 >= n: return
        if kind == "kick":
            k = min(int(0.25 * SR), n - i0); tt = np.arange(k) / SR
            fr = 45 + 95 * np.exp(-tt / 0.04); ph = 2 * np.pi * np.cumsum(fr) / SR
            out[i0:i0 + k] += 0.9 * np.sin(ph) * np.exp(-tt / 0.07)
        else:
            d = 0.05 if kind == "hat" else 0.15; k = min(int(d * SR), n - i0); tt = np.arange(k) / SR
            nz = rng.uniform(-1, 1, k)
            if kind == "hat": nz = np.diff(np.concatenate([[0], nz]))
            out[i0:i0 + k] += (0.18 if kind == "hat" else 0.4) * nz * np.exp(-tt / (d / 4))

    b, t = 0, 0.05
    while t < length:
        ch = S["prog"][b % 4]
        for m in ch: tone(m, t, bar * 0.98, "sine" if style == "calm" else "tri", 0.09 if style == "calm" else 0.05)
        if style == "calm":
            tone(ch[0] - 12, t, bar * 0.95, "sine", 0.22)
            for k, m in enumerate(ch + [ch[0] + 12]): tone(m + 12, t + k * beat, beat * 1.8, "sine", 0.06)
        else:
            for k in range(4): tone(ch[0] - 12, t + k * beat, beat * 0.8, "sine", 0.22)
            if style == "upbeat":
                for k in range(8): tone(ch[k % 3] + 12, t + k * beat / 2, beat * 0.4, "sq", 0.02)
            else:
                for k in range(4): tone(ch[k % 3] + 24, t + k * beat, beat * 1.5, "sine", 0.07); tone(ch[k % 3] + 36, t + k * beat, beat * 0.6, "sine", 0.02)
            for k in range(4):
                bt = t + k * beat
                if k % 2 == 0 or style == "festive": hit(bt, "kick")
                if k % 2 == 1: hit(bt, "snare")
                hit(bt, "hat"); hit(bt + beat / 2, "hat")
        b += 1; t += bar
    env = np.ones(n); fi = int(0.6 * SR); env[:fi] = np.linspace(0, 1, fi)
    fo0 = int((length - 2) * SR); env[fo0:] = np.linspace(1, 0, n - fo0)
    out *= env; out = np.tanh(out * 1.2) * 0.85
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((out * 32767).astype("<i2").tobytes())


# ---------- media ----------
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-800:])
    return r


def probe_duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 3.0


def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted([q for q in p.rglob("*") if q.suffix.lower() in IMG_EXT | VID_EXT], key=lambda q: str(q))
        elif p.suffix.lower() in IMG_EXT | VID_EXT:
            files.append(p)
    return files[:40]


def frame_from_image(src, dst):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    wide = im.width > im.height * 1.1
    s = max(W / im.width, H / im.height)
    bg = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    if wide:
        bg = bg.filter(ImageFilter.GaussianBlur(28)).point(lambda v: int(v * 0.6))
        s2 = min(W / im.width, H / im.height)
        fg = im.resize((int(im.width * s2), int(im.height * s2)), Image.LANCZOS)
        bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    bg.save(dst, quality=94)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+"); ap.add_argument("--name", required=True); ap.add_argument("--line", default="")
    ap.add_argument("--logo"); ap.add_argument("--style", default="upbeat", choices=["upbeat", "calm", "festive", "none"])
    ap.add_argument("--max", type=float, default=15); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not shutil.which("ffmpeg"): sys.exit("ffmpeg is missing")
    files = collect(a.inputs)
    if not files: sys.exit("no photos or clips found")
    tmp = Path(tempfile.mkdtemp())
    logo = ImageOps.exif_transpose(Image.open(a.logo)).convert("RGBA") if a.logo else None

    # durations: clips up to 6 s, photos share what is left (1.5–3 s each), total up to --max
    items, skipped = [], []
    for f in files:
        kind = "video" if f.suffix.lower() in VID_EXT else "image"
        if kind == "image":
            try: Image.open(f).verify()
            except Exception: skipped.append(f.name); continue
        items.append({"f": f, "kind": kind, "dur": min(6, max(1.5, probe_duration(f))) if kind == "video" else 3})
    room = a.max - END
    vids = [i for i in items if i["kind"] == "video"]; imgs = [i for i in items if i["kind"] == "image"]
    vt = sum(i["dur"] for i in vids)
    if vt > room * 0.7:
        k = room * 0.7 / vt
        for i in vids: i["dur"] = max(1.5, i["dur"] * k)
        vt = sum(i["dur"] for i in vids)
    per = max(1.5, min(3, (room - vt) / len(imgs))) if imgs else 0
    for i in imgs: i["dur"] = per
    t, keep = 0, []
    for i in items:
        if t + i["dur"] > room + 0.01: continue
        keep.append(i); t += i["dur"]
    if not keep: sys.exit("no usable photos or clips")

    segs = []
    vf_cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"
    for n, it in enumerate(keep):
        seg = tmp / f"seg{n:02d}.mp4"
        if it["kind"] == "image":
            fr = tmp / f"f{n:02d}.jpg"; frame_from_image(it["f"], fr)
            frames = int(it["dur"] * FPS)
            zoom = f"zoompan=z='min(1+0.06*on/{frames},1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
            run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(fr), "-vf", zoom, "-t", f"{it['dur']:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(seg)])
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", str(it["f"]), "-t", f"{it['dur']:.3f}", "-filter_complex",
                 f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:4,eq=brightness=-0.15[bg];[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS},format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(seg)])
        segs.append(seg)
    ec = tmp / "end.jpg"; end_card(ec, a.name, a.line, logo)
    endseg = tmp / "end.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(ec), "-t", f"{END}", "-vf", f"fade=t=in:st=0:d=0.5,fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(endseg)])

    lst = tmp / "list.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    body = tmp / "body.mp4"; run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(body)])
    ov = tmp / "overlay.png"; overlay_png(ov, a.name, a.line, logo)
    body2 = tmp / "body2.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(body), "-i", str(ov), "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(body2)])
    lst2 = tmp / "list2.txt"; lst2.write_text(f"file '{body2}'\nfile '{endseg}'\n")
    silent = tmp / "silent.mp4"; run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst2), "-c", "copy", str(silent)])
    total = probe_duration(silent)

    out = Path(a.out)
    if a.style == "none":
        run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-c:v", "copy", "-movflags", "+faststart", str(out)])
    else:
        wav = tmp / "music.wav"; music(wav, a.style, total)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)])
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"OK {out} {total:.1f}s {out.stat().st_size/1048576:.1f}MB used={len(keep)} left_out={len(items)-len(keep)} unreadable={','.join(skipped) or 0}")


if __name__ == "__main__":
    main()
