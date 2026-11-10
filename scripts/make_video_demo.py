r"""The submission demo: 66 seconds, real terminal, two readings of one brief.

Hook first, features second. The story is the meeting, not the pipeline:
same six sources, one interview brief and one sales brief, and the questions
change underneath.

Every number and question comes from the recorded replay in demo_valve.py; the
brief frames are screenshots of the HTML those runs produced.

    python scripts/make_briefs.py        # once, to refresh the screenshots
    python scripts/make_video_demo.py    # docs/dossier-demo-final.mp4
"""

from __future__ import annotations

import json
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
from make_video_valve import (  # noqa: E402
    ACCENT, AMBER, DIM, H, INK, MINT, MUTED, PANEL, RING, W,
    appear, back_out, drift, ease, fit, font, frame, ken_burns, layer,
    panel, progress, stamp, text, tick, wrap,
)

BRIEFS = Path(tempfile.gettempdir()) / "opencode" / "briefs"
OUT = ROOT / "docs" / "dossier-demo.mp4"

SERIF_B = vis.SERIF_B
SERIF = vis.SERIF
MONO = vis.MONO
MONO_B = vis.MONO_B
UI = vis.UI
UI_B = vis.UI_B

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
    # Music level per scene: quiet under the hook, full at the brief and the
    # split, dropped back for the diff, lifted for the close.
    "plan": [
        (0.0, 5.0, 0.30, "intro"),
        (5.0, 18.0, 0.70, "build"),
        (18.0, 31.0, 1.00, "main"),
        (31.0, 43.0, 1.00, "lift"),
        (43.0, 52.0, 0.55, "break"),
        (52.0, 59.0, 0.85, "main"),
        (59.0, 66.0, 0.90, "outro"),
    ],
    # Story sounds, per the Murch hierarchy: the rows landing, the keystrokes,
    # then the three marks that carry the picture (split, zero, final hit).
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
        ("Dossier. A Hermes plug in.", 59.6),
    ],
}


def load() -> dict:
    data = json.loads((BRIEFS / "briefs.json").read_text(encoding="utf-8"))
    data["counts"] = data["interview"]["counts"]
    return data


def chip(image: Image.Image, label: str, t: float, *, alarm: bool = False) -> None:
    draw = ImageDraw.Draw(image)
    width = int(font(MONO_B, 13).getlength(label)) + 28
    x0 = W - 46 - width
    colour = AMBER if not alarm else MINT
    draw.rounded_rectangle([x0, 34, W - 46, 66], radius=16, outline=colour, width=1)
    draw.ellipse([x0 + 12, 45, x0 + 20, 53], fill=colour)
    text(draw, (x0 + 28, 42), label, path=MONO_B, size=13, fill=colour)


# ------------------------------------------------------------------ scenes


def scene_hook(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 5.0)
    draw = ImageDraw.Draw(image)

    p1 = appear(t, 0.1, 0.5)
    if p1 > 0:
        text(draw, (84, 210 - (1 - p1) * 14), "You have a meeting in 45 minutes.", path=SERIF_B, size=52)
    p2 = appear(t, 1.5, 0.5)
    if p2 > 0:
        text(draw, (86, 296), "What do you actually know?", path=SERIF, size=34, fill=MUTED)

    p3 = appear(t, 2.7, 0.7)
    if p3 > 0:
        draw.rectangle([0, 0, W, 4], fill=ACCENT)
        text(draw, (86, 420), "Dossier", path=SERIF_B, size=84)
        text(draw, (90, 528), "a sourced brief, built before you walk in", path=SERIF, size=24, fill=MUTED)
    return image


def scene_command(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 4.0)
    canvas_l, draw = layer()

    p = ease(t / 0.4)
    top = 132 - (1 - p) * 22
    panel(draw, (66, top, W - 66, top + 300), fill=(16, 19, 27), radius=12)

    # window chrome
    draw.rounded_rectangle([66, top, W - 66, top + 34], radius=12, fill=(28, 32, 43))
    for index, colour in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse([82 + index * 18, top + 12, 92 + index * 18, top + 22], fill=colour)
    text(draw, (W // 2 - 70, top + 10), "hermes — dossier", path=MONO, size=12, fill=DIM)

    typed = min(len('prep "Valve Corporation" interview'), int(max(0.0, t - 0.4) * 26))
    command = "/dossier prep \"Valve Corporation\" interview"[:11 + typed]
    cursor = "▌" if int(t * 4) % 2 == 0 else " "
    text(draw, (92, top + 66), "$ " + command + cursor, path=MONO_B, size=21)

    if t > 2.4:
        tick(draw, 94, top + 128, MINT, 11)
        text(draw, (120, top + 124), "Valve Corporation  →  one candidate", path=MONO, size=15, fill=MINT)
    if t > 2.9:
        text(draw, (120, top + 156), "context: job interview  ·  purpose recorded", path=MONO, size=15, fill=DIM)
    stamp(image, canvas_l, 1.0)
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_sources(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 9.0)
    canvas_l, draw = layer()
    panel(draw, (66, 88, W - 66, H - 92), fill=(16, 19, 27), radius=12)

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
        text(draw, (W - 300, y), note, path=MONO, size=14, fill=DIM)
        y += 40

    if t > 4.6:
        p = appear(t, 4.6, 0.4)
        text(draw, (96, y + 26), "what it could not do", path=MONO_B, size=14, fill=AMBER)
        notes = [
            "no SEC filing: Valve is private",
            "3 news pages had no publication date, so they are not dated news",
        ]
        ny = y + 54
        for index, note in enumerate(notes):
            for line in wrap(note, font(MONO, 13), W - 260)[:2]:
                text(draw, (100, ny), line, path=MONO, size=13, fill=(206, 184, 146))
                ny += 20
        stamp(image, canvas_l, 1.0)
    else:
        stamp(image, canvas_l, 1.0)

    if t > 6.6:
        p = appear(t, 6.6, 0.4)
        canvas_l, draw = layer()
        text(draw, (96, H - 132), "six sources   ·   six claims   ·   one brief", path=MONO_B, size=17, fill=INK)
        stamp(image, canvas_l, p)
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_brief(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 13.0)
    canvas_l, draw = layer()
    p = appear(t, 0.1, 0.4)
    text(draw, (66, 38), "Prepared for the interview", path=SERIF_B, size=28)
    text(draw, (68, 78), "one line, three facts, and the questions you can actually ask", size=15, fill=MUTED)
    stamp(image, canvas_l, p)

    canvas_l, draw = layer()
    p = appear(t, 0.2, 0.6)
    box = (62, 112, 640, H - 26)
    draw.rounded_rectangle(box, radius=12, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = ken_burns(Image.open(BRIEFS / "interview.png").convert("RGB"), min(1.0, t / 13.0))
    thumb = fit(shot, box[2] - box[0] - 12, box[3] - box[1] - 12)
    canvas_l.paste(thumb, (int(box[0] + 6), int(box[1] + 6)))
    stamp(image, canvas_l, p)

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
        canvas_l, draw = layer()
        dx = (1 - p) * 32
        panel(draw, (690, y + dx, W - 58, y + 82 + dx), fill=(26, 30, 43))
        text(draw, (712, y + 14 + dx), label, path=UI_B, size=11, fill=ACCENT)
        for line in wrap(detail, font(UI, 15), W - 58 - 736)[:2]:
            text(draw, (712, y + 36 + dx), line, size=15, fill=INK)
        stamp(image, canvas_l, p)
        y += 100
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_split(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 12.0)
    canvas_l, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 36), "Same evidence. Different questions.", path=SERIF_B, size=30)
    text(draw, (68, 78), "the context changes the brief, not the sources", size=15, fill=MUTED)
    stamp(image, canvas_l, p)

    columns = [
        ("INTERVIEW", MINT, data["interview"]["questions"], 66),
        ("SALES CALL", AMBER, data["sales"]["questions"], 656),
    ]
    for label, colour, questions, x in columns:
        p = appear(t, 0.6 + (0.3 if x > 600 else 0), 0.5)
        canvas_l, draw = layer()
        panel(draw, (x, 120, x + 558, 470), fill=(22, 26, 36))
        draw.rounded_rectangle([x + 18, 136, x + 18 + 120, 164], radius=14, outline=colour, width=1)
        text(draw, (x + 34, 143), label, path=MONO_B, size=11, fill=colour)
        yy = 190
        for index, question in enumerate(questions):
            for line in wrap(question, font(UI, 16), 512)[:3]:
                text(draw, (x + 22, yy), line, size=16, fill=INK)
                yy += 22
            yy += 16
        stamp(image, canvas_l, p)

    canvas_l, draw = layer()
    p = appear(t, 3.4, 0.5)
    text(draw, (66, 500), "six sources, six claims, zero invented", path=MONO_B, size=16, fill=MUTED)
    text(draw, (66, 540), "the questions change because the meeting changed", path=MONO_B, size=18, fill=INK)
    stamp(image, canvas_l, p)
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_diff(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 9.0)
    canvas_l, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 40), "And the second look", path=SERIF_B, size=30)
    text(draw, (68, 82), "refresh the day of the meeting", size=15, fill=MUTED)
    stamp(image, canvas_l, p)

    canvas_l, draw = layer()
    p = appear(t, 0.2, 0.5)
    panel(draw, (66, 124, W - 66, 396), fill=(21, 25, 36))
    text(draw, (96, 148), "DIFF AGAINST THE PREVIOUS SNAPSHOT", path=UI_B, size=11, fill=ACCENT)
    draw.line([96, 174, W - 96, 174], fill=(48, 54, 72))
    stamp(image, canvas_l, p)

    p = back_out((t - 0.6) / 0.7)
    if p > 0:
        canvas_l, draw = layer()
        text(draw, (98, 206 + (1 - p) * 18), "0", path=SERIF_B, size=int(72 * p), fill=MINT)
        stamp(image, canvas_l, min(1.0, p))

    canvas_l, draw = layer()
    p = appear(t, 1.3, 0.4)
    text(draw, (186, 238), "changes", path=SERIF, size=28, fill=MUTED)
    text(draw, (98, 316), "nothing moved, and it says so instead of inventing activity", size=17, fill=INK)
    stamp(image, canvas_l, p)

    canvas_l, draw = layer()
    p = appear(t, 2.6, 0.5)
    text(draw, (66, 448), "when something does move, only that appears:  + ceo,  - ceo,  nothing else",
         path=MONO_B, size=15, fill=AMBER)
    stamp(image, canvas_l, p)
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_pdf(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 7.0)
    canvas_l, draw = layer()
    p = appear(t, 0.05, 0.4)
    text(draw, (66, 38), "Take it with you", path=SERIF_B, size=28)
    text(draw, (68, 78), "A4 PDF and HTML, written by the plugin", size=15, fill=MUTED)
    stamp(image, canvas_l, p)

    canvas_l, draw = layer()
    p = appear(t, 0.2, 0.5)
    lift = (1 - p) * 20
    box = (66, 110 + lift, 452, H - 26 + lift)
    draw.rounded_rectangle(box, radius=10, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = fit(Image.open(BRIEFS / "interview-page-1.png").convert("RGB"), 370, 560)
    canvas_l.paste(shot, (int(box[0]) + 6, int(box[1]) + 6))
    stamp(image, canvas_l, p)

    lines = ["no WeasyPrint, no typst", "word wrap, pagination, source appendix", "same run as the HTML"]
    y = 150
    for index, line in enumerate(lines):
        p = appear(t, 0.9 + index * 0.4, 0.4)
        canvas_l, draw = layer()
        draw.rectangle([500, int(y + 6), 504, int(y + 20)], fill=ACCENT)
        text(draw, (518, y), line, size=18)
        stamp(image, canvas_l, p)
        y += 42
    chip(image, "MEETING IN 45 MIN", t)
    return image


def scene_close(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 7.0)
    canvas_l, draw = layer()
    p = appear(t, 0.1, 0.5)
    draw.rectangle([0, 0, W, 4], fill=ACCENT)
    text(draw, (84, 150), "Dossier", path=SERIF_B, size=64)
    text(draw, (88, 234), "sourced · dated · refreshable", path=SERIF, size=26, fill=MUTED)
    stamp(image, canvas_l, p)

    lines = ["hermes plugins install dossier", '/dossier prep "Valve Corporation" interview']
    y = 320
    for index, line in enumerate(lines):
        p = appear(t, 0.6 + index * 0.4, 0.4)
        canvas_l, draw = layer()
        text(draw, (88, y), line, path=MONO, size=18, fill=INK if index == 0 else MUTED)
        stamp(image, canvas_l, p)
        y += 38

    canvas_l, draw = layer()
    p = appear(t, 1.8, 0.5)
    text(draw, (88, 424), "PDF · HTML · Desktop page · cron · watchlist", path=MONO, size=16, fill=MUTED)
    text(draw, (88, 470), "114 tests · doctor and validate clean · MIT", size=15, fill=MUTED)
    text(draw, (88, 520), "github.com/Frazzlesprite/dossier-plugin", path=MONO_B, size=20, fill=ACCENT)
    stamp(image, canvas_l, p)
    chip(image, "BRIEF READY", t, alarm=True)
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


def render(data: dict, target: Path) -> Path:
    writer = imageio_ffmpeg.write_frames(
        str(target), (W, H), fps=30, codec="libx264",
        output_params=["-crf", "18", "-pix_fmt", "yuv420p"],
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

    import os

    if os.environ.get("AUDIO_ONLY") and silent.exists():
        print("reusing the rendered frames")
    else:
        print("rendering...")
        render(data, silent)

    print("audio...")
    audio = make_audio.build(TOTAL, SCENES, build_dir / "demo-audio.wav", cues=CUES)

    print("muxing...")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
            "-i", str(silent), "-i", str(audio),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(OUT),
        ],
        check=True,
    )
    print(f"wrote {OUT} ({TOTAL:.0f}s, 30fps, audio)")
    return OUT


if __name__ == "__main__":
    main()
