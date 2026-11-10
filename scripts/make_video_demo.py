r"""The submission demo: 66 seconds, 1080p, four-stem mix.

Layout is authored in 1280x720 design units and drawn at 1.5x, so text and
rules land on real 1080p pixels rather than being upscaled at the end.

    python scripts/make_briefs.py        # 2x screenshots
    python scripts/make_video_demo.py    # docs/dossier-demo.mp4
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imageio_ffmpeg  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import make_audio  # noqa: E402
import make_video_valve as vis  # noqa: E402

# Design space, then the real frame.
DW, DH = 1280, 720
S = 2.0                     # draw at 2560x1440, then downscale to 1080p
W, H = int(DW * S), int(DH * S)   # 2560x1440, both multiples of 16

INK = vis.INK
MUTED = vis.MUTED
DIM = vis.DIM
ACCENT = vis.ACCENT
MINT = vis.MINT
AMBER = vis.AMBER
PANEL = vis.PANEL
RING = vis.RING
SERIF = vis.SERIF
SERIF_B = vis.SERIF_B
MONO = vis.MONO
MONO_B = vis.MONO_B
UI = vis.UI
UI_B = vis.UI_B

BRIEFS = Path(tempfile.gettempdir()) / "opencode" / "briefs"
OUT = ROOT / "docs" / "dossier-demo.mp4"

BACKGROUND = vis.BACKGROUND.resize((W, H), Image.LANCZOS)
GLOW_A = vis.GLOW_BLUE.resize((int(760 * S), int(760 * S)), Image.LANCZOS)
GLOW_B = vis.GLOW_MINT.resize((int(560 * S), int(560 * S)), Image.LANCZOS)

SCENES = [
    ("hook", 5.0),
    ("command", 4.0),
    ("sources", 9.0),
    ("brief", 13.0),
    ("split", 12.0),
    ("diff", 9.0),
    ("pdf", 7.0),
    ("close", 7.0),
]
TOTAL = sum(d for _, d in SCENES)

CUES = {
    "plan": [
        (0.0, 5.0, 0.30, "intro"),
        (5.0, 18.0, 0.70, "build"),
        (18.0, 31.0, 1.00, "main"),
        (31.0, 43.0, 1.00, "lift"),
        (43.0, 52.0, 0.55, "break"),
        (52.0, 59.0, 0.85, "main"),
        (59.0, 66.0, 0.90, "outro"),
    ],
    "rows": [9.7, 10.7, 11.7, 12.7],
    "keys": [5.6, 5.9, 6.2, 6.5, 6.8, 7.1, 7.4, 7.7],
    "marks": [31.2, 43.9, 59.4],
    "voice": [
        ("Forty five minutes before the meeting.", 0.5),
        ("Type the company, and what you are walking into.", 5.4),
        ("Every claim cites the page it came from.", 12.0),
        ("This one is for the interview.", 19.2),
        ("Same evidence. A different meeting, so different questions.", 31.8),
        ("Refresh it the morning of, and it tells you what changed.", 44.2),
        ("Dossier for Hermes.", 59.6),
    ],
}


# ---------------------------------------------------------------- helpers


def font(path: str, size: int):
    return vis.font(path, max(1, int(size * S)))


def text(draw, xy, value, *, path=UI, size=20, fill=INK):
    vis.text(draw, (xy[0] * S, xy[1] * S), value, path=path, size=int(size * S), fill=fill)


def wrap(value: str, f, width: float) -> list[str]:
    return vis.wrap(value, f, int(width * S))


def panel(draw, box, fill=PANEL, outline=RING, radius=16):
    vis.panel(draw, [v * S for v in box], fill=fill, outline=outline, radius=int(radius * S))


def tick(draw, x: float, y: float, colour, size: int = 11):
    vis.tick(draw, x * S, y * S, colour, int(size * S))


def rect(draw, box, **kwargs):
    draw.rectangle([int(v * S) for v in box], **kwargs)


def rrect(draw, box, radius: int = 8, **kwargs):
    draw.rounded_rectangle([int(v * S) for v in box], radius=int(radius * S), **kwargs)


def ellipse(draw, box, **kwargs):
    draw.ellipse([int(v * S) for v in box], **kwargs)


def line(draw, x0, y0, x1, y1, **kwargs):
    width = kwargs.pop("width", 1)
    draw.line([x0 * S, y0 * S, x1 * S, y1 * S], width=max(1, int(width * S)), **kwargs)



def progress(image, elapsed: float, total: float) -> None:
    draw = ImageDraw.Draw(image)
    # Kept above H-8 so it survives the crop to 1920x1080 for X.
    top = H - 34
    draw.rectangle([0, top, W, top + 4], fill=(24, 27, 38))
    draw.rectangle([0, top, int(W * min(1.0, elapsed / total)), top + 4], fill=ACCENT)


def layer():
    # The compositing canvas must match the real frame, not the design units,
    # or everything past 1280 px is clipped.
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return canvas, ImageDraw.Draw(canvas)


def stamp(image, canvas, alpha: float = 1.0):
    vis.stamp(image, canvas, alpha)


def appear(t: float, delay: float, dur: float = 0.45) -> float:
    return vis.appear(t, delay, dur)


def ease(t: float) -> float:
    return vis.ease(t)


def back_out(t: float) -> float:
    return vis.back_out(t)


def frame() -> Image.Image:
    return BACKGROUND.copy()


def drift(image: Image.Image, t: float, total: float) -> Image.Image:
    import math

    phase = t / max(total, 1.0)
    x = int(W * 0.18 + math.sin(phase * 2.0) * 150 * S)
    y = int(H * 0.22 + math.cos(phase * 1.6) * 90 * S)
    image.paste(GLOW_A, (x - GLOW_A.width // 2, y - GLOW_A.height // 2), GLOW_A)
    x2 = int(W * 0.82 + math.sin(phase * 1.3 + 1.7) * 120 * S)
    y2 = int(H * 0.78 + math.cos(phase * 1.9 + 0.6) * 80 * S)
    image.paste(GLOW_B, (x2 - GLOW_B.width // 2, y2 - GLOW_B.height // 2), GLOW_B)
    return image


def push(shot: Image.Image, p: float, box, focus=(0.5, 0.40), zoom=1.05) -> Image.Image:
    """Ken Burns by sampling a float rectangle: no integer crop steps."""
    sw, sh = shot.size
    w, h = (box[2] - box[0]) * S, (box[3] - box[1]) * S
    z = 1.0 + (zoom - 1.0) * p
    cw, ch = sw / z, sh / z
    x0 = max(0.0, min(sw - cw, focus[0] * sw - cw / 2))
    y0 = max(0.0, min(sh - ch, focus[1] * sh - ch / 2))
    return shot.transform((int(w), int(h)), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), resample=Image.BICUBIC)


def page(shot: Image.Image, box) -> Image.Image:
    w, h = (box[2] - box[0]) * S, (box[3] - box[1]) * S
    scale = min(w / shot.width, h / shot.height)
    return shot.resize((max(1, int(shot.width * scale)), max(1, int(shot.height * scale))), Image.LANCZOS)


def chip(image: Image.Image, label: str, alarm: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    f = vis.font(MONO_B, int(13 * S))
    width = int(f.getlength(label)) + int(28 * S)
    x0 = W - int(46 * S) - width
    y0, y1 = int(34 * S), int(66 * S)
    colour = MINT if alarm else AMBER
    draw.rounded_rectangle([x0, y0, W - int(46 * S), y1], radius=int(16 * S), outline=colour, width=max(1, int(S)))
    r = int(4 * S)
    draw.ellipse([x0 + int(12 * S), (y0 + y1) // 2 - r, x0 + int(12 * S) + 2 * r, (y0 + y1) // 2 + r], fill=colour)
    draw.text((x0 + int(28 * S), y0 + int(8 * S)), label, font=f, fill=colour)


# ------------------------------------------------------------------ scenes


def scene_hook(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 5.0)
    canvas, draw = layer()

    p1 = appear(t, 0.1, 0.5)
    if p1 > 0:
        text(draw, (84, 210 - (1 - p1) * 14), "You have a meeting in 45 minutes.", path=SERIF_B, size=52)
    p2 = appear(t, 1.5, 0.5)
    if p2 > 0:
        text(draw, (86, 296), "What do you actually know?", path=SERIF, size=34, fill=MUTED)

    p3 = appear(t, 2.7, 0.7)
    if p3 > 0:
        rect(draw, [0, 0, DW, 4], fill=ACCENT)
        text(draw, (86, 420), "Dossier", path=SERIF_B, size=84)
        text(draw, (90, 528), "a sourced brief, built before you walk in", path=SERIF, size=24, fill=MUTED)
    stamp(image, canvas, 1.0)
    return image


def scene_command(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 4.0)
    canvas, draw = layer()

    p = ease(t / 0.4)
    top = 132 - (1 - p) * 22
    panel(draw, (66, top, DW - 66, top + 300), fill=(16, 19, 27), radius=12)
    rrect(draw, (66, top, DW - 66, top + 34), radius=12, fill=(28, 32, 43))
    for index, colour in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        ellipse(draw, (82 + index * 18, top + 12, 92 + index * 18, top + 22), fill=colour)
    text(draw, (DW // 2 - 70, top + 10), "hermes — dossier", path=MONO, size=12, fill=DIM)

    typed = min(len('prep "Valve Corporation" interview'), int(max(0.0, t - 0.4) * 26))
    command = "/dossier prep \"Valve Corporation\" interview"[:11 + typed]
    cursor = "▌" if int(t * 4) % 2 == 0 else " "
    text(draw, (92, top + 66), "$ " + command + cursor, path=MONO_B, size=21)

    if t > 2.4:
        tick(draw, 94, top + 128, MINT, 11)
        text(draw, (120, top + 124), "Valve Corporation  →  one candidate", path=MONO, size=15, fill=MINT)
    if t > 2.9:
        text(draw, (120, top + 156), "context: job interview  ·  purpose recorded", path=MONO, size=15, fill=DIM)
    stamp(image, canvas, 1.0)
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_sources(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 9.0)
    canvas, draw = layer()
    panel(draw, (66, 88, DW - 66, DH - 92), fill=(16, 19, 27), radius=12)

    rows = [
        ("official", "valvesoftware.com", "3 pages"),
        ("search", "en.wikipedia.org", "fetched in full"),
        ("search", "forbes.com/companies/valve", "fetched in full"),
        ("registry", "SEC EDGAR", "no registrant: private"),
    ]
    y = 126
    for index, (kind, host, note) in enumerate(rows):
        p = appear(t, 0.35 + index * 1.0, 0.35)
        if p <= 0:
            continue
        dx = (1 - p) * -22
        tick(draw, 96 + dx, y + 3, MINT, 11)
        text(draw, (124 + dx, y), kind.ljust(10), path=MONO_B, size=17, fill=MINT)
        text(draw, (268 + dx, y), host, path=MONO, size=16, fill=INK)
        text(draw, (DW - 300, y), note, path=MONO, size=14, fill=DIM)
        y += 40

    if t > 4.6:
        text(draw, (96, y + 26), "what it could not do", path=MONO_B, size=14, fill=AMBER)
        notes = [
            "no SEC filing: Valve is private",
            "3 news pages had no publication date, so they are not dated news",
        ]
        ny = y + 54
        for note in notes:
            for text_line in wrap(note, font(MONO, 13), DW - 260)[:2]:
                text(draw, (100, ny), text_line, path=MONO, size=13, fill=(206, 184, 146))
                ny += 20

    if t > 6.6:
        p = appear(t, 6.6, 0.4)
        canvas2, draw2 = layer()
        text(draw2, (96, DH - 132), "six sources   ·   six claims   ·   one brief", path=MONO_B, size=17, fill=INK)
        stamp(image, canvas2, p)
    stamp(image, canvas, 1.0)
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_brief(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 13.0)
    canvas, draw = layer()
    p = appear(t, 0.1, 0.4)
    text(draw, (66, 38), "Prepared for the interview", path=SERIF_B, size=28)
    text(draw, (68, 78), "one line, three facts, and the questions you can actually ask", size=15, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.2, 0.6)
    box = (62, 112, 640, DH - 26)
    rrect(draw, box, radius=12, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = Image.open(BRIEFS / "interview.png").convert("RGB")
    thumb = push(shot, min(1.0, t / 13.0), box)
    canvas.paste(thumb, (int(box[0] * S) + 6, int(box[1] * S) + 6))
    stamp(image, canvas, p)

    callouts = [
        ("ONE LINE", data["interview"]["headline"].split(": ", 1)[-1]),
        ("FACTS", "founded 1996  ·  hq Bellevue"),
        ("CAUTION", "do not quote headcount: sources disagree"),
        ("QUESTIONS", "team, first ninety days, how success is measured"),
    ]
    y = 122
    for index, (label, detail) in enumerate(callouts):
        p = appear(t, 1.2 + index * 1.5, 0.45)
        if p <= 0:
            y += 100
            continue
        canvas2, draw2 = layer()
        dx = (1 - p) * 32
        panel(draw2, (690, y + dx, DW - 58, y + 82 + dx), fill=(26, 30, 43))
        text(draw2, (712, y + 14 + dx), label, path=UI_B, size=11, fill=ACCENT)
        for text_line in wrap(detail, font(UI, 15), DW - 58 - 736)[:2]:
            text(draw2, (712, y + 36 + dx), text_line, size=15, fill=INK)
        stamp(image, canvas2, p)
        y += 100
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_split(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 12.0)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 36), "Same evidence. Different questions.", path=SERIF_B, size=30)
    text(draw, (68, 78), "the context changes the brief, not the sources", size=15, fill=MUTED)
    stamp(image, canvas, p)

    columns = [
        ("INTERVIEW", MINT, data["interview"]["questions"], 66),
        ("SALES CALL", AMBER, data["sales"]["questions"], 656),
    ]
    for label, colour, questions, x in columns:
        p = appear(t, 0.6 + (0.3 if x > 600 else 0), 0.5)
        canvas2, draw2 = layer()
        panel(draw2, (x, 120, x + 558, 470), fill=(22, 26, 36))
        rrect(draw2, (x + 18, 136, x + 138, 164), radius=14, outline=colour, width=1)
        text(draw2, (x + 34, 143), label, path=MONO_B, size=11, fill=colour)
        yy = 190
        for question in questions:
            for text_line in wrap(question, font(UI, 16), 512)[:3]:
                text(draw2, (x + 22, yy), text_line, size=16, fill=INK)
                yy += 22
            yy += 16
        stamp(image, canvas2, p)

    canvas3, draw3 = layer()
    p = appear(t, 3.4, 0.5)
    text(draw3, (66, 500), "six sources, six claims, zero invented", path=MONO_B, size=16, fill=MUTED)
    text(draw3, (66, 540), "the questions change because the meeting changed", path=MONO_B, size=18, fill=INK)
    stamp(image, canvas3, p)
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_diff(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 9.0)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 40), "And the second look", path=SERIF_B, size=30)
    text(draw, (68, 82), "refresh the day of the meeting", size=15, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.2, 0.5)
    panel(draw, (66, 124, DW - 66, 396), fill=(21, 25, 36))
    text(draw, (96, 148), "DIFF AGAINST THE PREVIOUS SNAPSHOT", path=UI_B, size=11, fill=ACCENT)
    line(draw, 96, 174, DW - 96, 174, fill=(48, 54, 72))
    stamp(image, canvas, p)

    p = back_out((t - 0.6) / 0.7)
    if p > 0:
        canvas2, draw2 = layer()
        text(draw2, (98, 206 + (1 - p) * 18), "0", path=SERIF_B, size=max(1, int(72 * p)), fill=MINT)
        stamp(image, canvas2, min(1.0, p))

    canvas3, draw3 = layer()
    p = appear(t, 1.3, 0.4)
    text(draw3, (186, 238), "changes", path=SERIF, size=28, fill=MUTED)
    text(draw3, (98, 316), "nothing moved, and it says so instead of inventing activity", size=17, fill=INK)
    stamp(image, canvas3, p)

    canvas4, draw4 = layer()
    p = appear(t, 2.6, 0.5)
    text(draw4, (66, 448), "when something does move, only that appears:  + ceo,  - ceo,  nothing else",
         path=MONO_B, size=15, fill=AMBER)
    stamp(image, canvas4, p)
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_pdf(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 7.0)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 38), "Take it with you", path=SERIF_B, size=28)
    text(draw, (68, 78), "A4 PDF and HTML, written by the plugin", size=15, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.2, 0.5)
    lift = (1 - p) * 20
    box = (66, 110 + lift, 452, DH - 26 + lift)
    rrect(draw, box, radius=10, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = page(Image.open(BRIEFS / "interview-page-1.png").convert("RGB"), box)
    canvas.paste(shot, (int(box[0] * S) + 6, int(box[1] * S) + 6))
    stamp(image, canvas, p)

    lines = ["no WeasyPrint, no typst", "word wrap, pagination, source appendix", "same run as the HTML"]
    y = 150
    for index, text_line in enumerate(lines):
        p = appear(t, 0.9 + index * 0.4, 0.4)
        canvas2, draw2 = layer()
        rect(draw2, (500, y + 6, 504, y + 20), fill=ACCENT)
        text(draw2, (518, y), text_line, size=18)
        stamp(image, canvas2, p)
        y += 42
    chip(image, "MEETING IN 45 MIN")
    return image


def scene_close(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 7.0)
    canvas, draw = layer()
    p = appear(t, 0.1, 0.5)
    rect(draw, (0, 0, DW, 4), fill=ACCENT)
    text(draw, (84, 150), "Dossier", path=SERIF_B, size=64)
    text(draw, (88, 234), "sourced · dated · refreshable", path=SERIF, size=26, fill=MUTED)
    stamp(image, canvas, p)

    lines = ["hermes plugins install dossier", '/dossier prep "Valve Corporation" interview']
    y = 320
    for index, text_line in enumerate(lines):
        p = appear(t, 0.6 + index * 0.4, 0.4)
        canvas2, draw2 = layer()
        text(draw2, (88, y), text_line, path=MONO, size=18, fill=INK if index == 0 else MUTED)
        stamp(image, canvas2, p)
        y += 38

    canvas3, draw3 = layer()
    p = appear(t, 1.8, 0.5)
    text(draw3, (88, 424), "PDF · HTML · Desktop page · cron · watchlist", path=MONO, size=16, fill=MUTED)
    text(draw3, (88, 470), "114 tests · doctor and validate clean · MIT", size=15, fill=MUTED)
    text(draw3, (88, 520), "github.com/Frazzlesprite/dossier-plugin", path=MONO_B, size=20, fill=ACCENT)
    stamp(image, canvas3, p)
    chip(image, "BRIEF READY", alarm=True)
    return image


SCENE_FUNCS = {
    "hook": scene_hook,
    "command": scene_command,
    "sources": scene_sources,
    "brief": scene_brief,
    "split": scene_split,
    "diff": scene_diff,
    "pdf": scene_pdf,
    "close": scene_close,
}


def load() -> dict:
    data = json.loads((BRIEFS / "briefs.json").read_text(encoding="utf-8"))
    data["counts"] = data["interview"]["counts"]
    return data


def render(data: dict, target: Path) -> Path:
    writer = imageio_ffmpeg.write_frames(
        str(target), (W, H), fps=30, codec="libx264",
        output_params=["-vf", "scale=1920:1080:flags=lanczos", "-crf", "14", "-preset", "slow",
                        "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p"],
    )
    writer.send(None)
    elapsed = 0.0
    for name, duration in SCENES:
        func = SCENE_FUNCS[name]
        for index in range(int(duration * 30)):
            t = index / 30
            image = func(t, data)
            progress(image, elapsed + t, TOTAL)
            edge = min(t, duration - t)
            alpha = 1.0 if edge >= 0.18 else edge / 0.18
            if alpha < 1.0:
                image = Image.blend(Image.new("RGB", (W, H), (4, 5, 9)), image, alpha)
            writer.send(image.tobytes())
        elapsed += duration
    writer.close()
    return target


def main() -> Path:
    data = load()
    build_dir = Path(tempfile.gettempdir()) / "opencode"
    silent = build_dir / "demo-silent.mp4"

    if os.environ.get("AUDIO_ONLY") and silent.exists():
        print("reusing rendered frames")
    else:
        print("rendering 1080p frames...")
        render(data, silent)

    print("audio...")
    audio = make_audio.build(TOTAL, SCENES, build_dir / "demo-audio.wav", cues=CUES)

    print("muxing...")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
            "-i", str(silent), "-i", str(audio),
            # X recommends at least 5 Mbps for a 1080p upload; a CRF pass on
            # static frames lands around 1.8 Mbps, so the deliverable is
            # re-encoded to a target rate instead of stream-copied.
            "-c:v", "libx264", "-preset", "medium",
            "-b:v", "8M", "-maxrate", "10M", "-bufsize", "20M",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(OUT),
        ],
        check=True,
    )
    print(f"wrote {OUT} ({TOTAL:.0f}s, {W}x{H}, 30fps, audio)")
    return OUT


if __name__ == "__main__":
    main()
