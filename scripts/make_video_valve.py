r"""The Valve demo: cut with motion and sound.

Every claim, date and quote comes from `demo_valve.main()`, which replays the
captured pages through the real pipeline. The brief and PDF frames are
screenshots of the actual output files. The soundtrack is synthesised by
`make_audio.py` and muxed on at the end.

    python scripts/make_video_valve.py     # docs/dossier-valve-demo.mp4
"""

from __future__ import annotations

import contextlib
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imageio_ffmpeg  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

import demo_valve  # noqa: E402
import make_audio  # noqa: E402

W, H = 1280, 720
FPS = 30
OUT = ROOT / "docs" / "dossier-valve-demo.mp4"
SHOTS = Path(tempfile.gettempdir()) / "opencode" / "valveshot"
BRIEF_PNG = SHOTS / "brief.png"
PDF_PNG = SHOTS / "pdf-1.png"

BG_TOP = (11, 13, 20)
BG_BOTTOM = (18, 21, 32)
INK = (244, 246, 250)
MUTED = (150, 159, 180)
DIM = (108, 117, 137)
ACCENT = (93, 135, 255)
MINT = (95, 227, 161)
AMBER = (255, 196, 107)
PANEL = (23, 26, 37)
RING = (52, 58, 76)

MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"
SERIF = r"C:\Windows\Fonts\georgia.ttf"
SERIF_B = r"C:\Windows\Fonts\georgiab.ttf"
UI = r"C:\Windows\Fonts\segoeui.ttf"
UI_B = r"C:\Windows\Fonts\segoeuib.ttf"

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(path: str, size: int):
    size = max(1, int(size))
    key = (path, size)
    if key not in _cache:
        try:
            _cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _cache[key] = ImageFont.load_default()
    return _cache[key]


def text(draw, xy, value, *, path=UI, size=20, fill=INK):
    draw.text(xy, value, font=font(path, size), fill=fill)


def wrap(value: str, f, width: int) -> list[str]:
    words, lines, current = value.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if f.getlength(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    return lines + ([current] if current else [])


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def appear(t: float, delay: float, dur: float = 0.45) -> float:
    return ease((t - delay) / dur)


def back_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def base_background() -> Image.Image:
    strip = Image.new("RGB", (1, H))
    for y in range(H):
        mix = y / (H - 1)
        strip.putpixel((0, y), tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * mix) for i in range(3)))
    image = strip.resize((W, H))
    vignette = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(vignette)
    inset = 60
    draw.ellipse([inset, inset, W - inset, H - inset], fill=70)
    vignette = vignette.filter(ImageFilter.GaussianBlur(180))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(image, Image.blend(image, dark, 0.45), vignette)


BACKGROUND = base_background()


def glow_sprite(colour: tuple[int, int, int], size: int = 760) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    steps = 26
    for i in range(steps, 0, -1):
        radius = int(size / 2 * i / steps)
        alpha = int(46 * (1 - i / steps) ** 1.6) + 6
        draw.ellipse(
            [size // 2 - radius, size // 2 - radius, size // 2 + radius, size // 2 + radius],
            fill=colour + (alpha,),
        )
    return layer.filter(ImageFilter.GaussianBlur(58))


GLOW_BLUE = glow_sprite(ACCENT)
GLOW_MINT = glow_sprite(MINT, 560)


def frame() -> Image.Image:
    image = BACKGROUND.copy()
    return image


def drift(image: Image.Image, t: float, total: float) -> Image.Image:
    """Two slow glows, so nothing is ever completely still."""
    phase = t / max(total, 1.0)
    x = int(W * 0.18 + math_sin(phase * 2.0) * 150)
    y = int(H * 0.22 + math_cos(phase * 1.6) * 90)
    image.paste(GLOW_BLUE, (x - 380, y - 380), GLOW_BLUE)
    x2 = int(W * 0.82 + math_sin(phase * 1.3 + 1.7) * 120)
    y2 = int(H * 0.78 + math_cos(phase * 1.9 + 0.6) * 80)
    image.paste(GLOW_MINT, (x2 - 280, y2 - 280), GLOW_MINT)
    return image


def math_sin(value: float) -> float:
    import math

    return math.sin(value)


def math_cos(value: float) -> float:
    import math

    return math.cos(value)


def layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return canvas, ImageDraw.Draw(canvas)


def stamp(image: Image.Image, canvas: Image.Image, alpha: float = 1.0) -> None:
    if alpha <= 0.01:
        return
    if alpha < 1.0:
        channel = canvas.getchannel("A").point(lambda v: int(v * alpha))
        canvas.putalpha(channel)
    image.paste(canvas, (0, 0), canvas)


def progress(image: Image.Image, t: float, total: float) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, H - 3, W, H], fill=(24, 27, 38))
    draw.rectangle([0, H - 3, int(W * min(1.0, t / total)), H], fill=ACCENT)


def tick(draw, x: float, y: float, colour, size: int = 11) -> None:
    draw.line([(x, y + size * 0.55), (x + size * 0.4, y + size)], fill=colour, width=3)
    draw.line([(x + size * 0.4, y + size), (x + size * 1.15, y + size * 0.1)], fill=colour, width=3)


def panel(draw, box, fill=PANEL, outline=RING, radius=16) -> None:
    draw.rounded_rectangle([int(v) for v in box], radius=radius, fill=fill, outline=outline, width=1)


def fit(shot: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(max_w / shot.width, max_h / shot.height)
    return shot.resize((max(1, int(shot.width * scale)), max(1, int(shot.height * scale))), Image.LANCZOS)


def ken_burns(shot: Image.Image, p: float) -> Image.Image:
    zoom = 1.0 + 0.07 * p
    cw, ch = int(shot.width / zoom), int(shot.height / zoom)
    cx = int((shot.width - cw) / 2)
    cy = int((shot.height - ch) * 0.42)
    return shot.crop((cx, cy, cx + cw, cy + ch))


SCENES = [
    ("title", 4.5),
    ("command", 3.5),
    ("sources", 12.5),
    ("brief", 17.0),
    ("series", 11.5),
    ("pdf", 7.5),
    ("diff", 9.5),
    ("close", 8.5),
]
TOTAL = sum(d for _, d in SCENES)


def collect() -> dict:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_valve.main()
    last = demo_valve.LAST
    first = last["first"]
    second = last["second"]

    facts = {c["predicate"]: c for c in first["claims"] if c["status"] == "supported"}
    employees = [c for c in first["claims"] if c["predicate"] == "employees"]
    notes = first["notes"]

    return {
        "headline": first["headline"],
        "founded": facts.get("founded", {}).get("value", ""),
        "hq": facts.get("hq", {}).get("value", ""),
        "employees": sorted(
            (
                {
                    "value": claim["value"],
                    "quote": claim["evidence"][0]["quote"],
                }
                for claim in employees
            ),
            key=lambda item: int(item["value"]) if item["value"].isdigit() else 9999,
        ),
        "counts": first["counts"],
        "diff_changes": (second.get("diff") or {}).get("changed_count", 0),
        "captured": last["index"]["captured_at"],
        "github_note": next((n for n in notes if n.startswith("github")), ""),
        "news_note": next((n for n in notes if n.startswith("news")), ""),
        "guard_note": next((n for n in notes if n.startswith("collision guard")), ""),
    }


def scene_title(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 4.5)
    canvas, draw = layer()

    p = appear(t, 0.15, 0.7)
    size = int(88 + 10 * p)
    alpha = p
    draw.rectangle([0, 0, W, 4], fill=ACCENT)
    text(draw, (90, 176 - (1 - p) * 26), "Dossier", path=SERIF_B, size=size)
    stamp(image, canvas, 1.0)

    canvas, draw = layer()
    p2 = appear(t, 0.55, 0.6)
    text(draw, (94, 312 - (1 - p2) * 14), "Everything you should know before you walk in.", path=SERIF, size=30, fill=MUTED)
    stamp(image, canvas, p2)

    canvas, draw = layer()
    for index, line in enumerate(
        (
            "A brief on one entity. Every claim cites the page it came from.",
            "Contradictions stay contested. Gaps stay gaps.",
            "The second look tells you what changed.",
        )
    ):
        p3 = appear(t, 1.1 + index * 0.35, 0.5)
        text(draw, (96, 446 + index * 38 - (1 - p3) * 12), line, size=20, fill=INK if index == 0 else MUTED)
    stamp(image, canvas, 1.0)

    canvas, draw = layer()
    p4 = appear(t, 2.3, 0.6)
    text(draw, (96, 630), "Hermes plugin   ·   MIT   ·   PDF, HTML, Desktop, cron", path=MONO, size=17, fill=ACCENT)
    stamp(image, canvas, p4)
    return image


def scene_command(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 3.5)
    canvas, draw = layer()
    p = ease(t / 0.45)
    box = (70, 90 - (1 - p) * 30, W - 70, H - 150 - (1 - p) * 30)
    panel(draw, box)
    text(draw, (100, box[1] + 26), "hermes", path=MONO_B, size=16, fill=DIM)

    typed = min(len("Valve Corporation"), int(max(0.0, t - 0.5) * 18))
    command = "/dossier Valve Corporation"[:9 + typed]
    cursor = "_" if int(t * 4) % 2 == 0 else " "
    text(draw, (100, box[1] + 62), "$ " + command + cursor, path=MONO_B, size=30)

    if t > 1.7:
        text(draw, (100, box[1] + 130), "resolving the entity", path=MONO, size=18, fill=MUTED)
    if t > 2.2:
        tick(draw, 102, box[1] + 168, MINT, 12)
        text(draw, (130, box[1] + 164), "one candidate: valvesoftware.com", path=MONO, size=18, fill=MINT)
    if t > 2.7:
        text(draw, (130, box[1] + 198), "no ambiguity to ask about", path=MONO, size=15, fill=DIM)
    stamp(image, canvas, 1.0)
    return image


def scene_sources(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 12.5)
    canvas, draw = layer()
    panel(draw, (66, 54, W - 66, H - 54), fill=(19, 22, 33))
    text(draw, (96, 78), "sources, in the order they landed", path=MONO, size=16, fill=DIM)

    drawn = [
        ("official", "valvesoftware.com   ·   3 pages   ·   /en, /about, /press"),
        ("search", "en.wikipedia.org   ·   fetched in full"),
        ("search", "forbes.com/companies/valve   ·   fetched in full"),
        ("registry", "SEC EDGAR   ·   no registrant: private company"),
    ]
    y = 126
    for index, (kind, detail) in enumerate(drawn):
        p = appear(t, 0.35 + index * 1.15, 0.4)
        if p <= 0:
            continue
        dx = (1 - p) * -26
        draw.rounded_rectangle(
            [int(92 + dx), int(y - 6), W - 96, int(y + 30)], radius=8, fill=(26, 30, 43, int(190 * p))
        )
        tick(draw, 108 + dx, y + 3, MINT, 11)
        text(draw, (136 + dx, y), kind.ljust(10), path=MONO_B, size=18, fill=MINT)
        text(draw, (272 + dx, y), detail, path=MONO, size=16, fill=MUTED)
        y += 42

    if t > 5.0:
        p = appear(t, 5.0, 0.5)
        text(draw, (96, y + 22), "what it could not do", path=MONO_B, size=16, fill=AMBER)
        notes = [n for n in (data["github_note"], data["news_note"], data["guard_note"]) if n]
        ny = y + 54
        for index, note in enumerate(notes):
            pn = appear(t, 5.3 + index * 0.35, 0.4)
            for line in wrap(note, font(MONO, 14), W - 260)[:2]:
                text(draw, (100, ny), line, path=MONO, size=14, fill=(206, 184, 146))
                ny += 21
            ny += 8

    if t > 8.6:
        p = appear(t, 8.6, 0.5)
        text(draw, (96, H - 104 - (1 - p) * 8), "six documents   ·   six claims   ·   zero invented",
             path=MONO_B, size=17, fill=INK)
    stamp(image, canvas, 1.0)
    return image


def scene_brief(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 17.0)
    canvas, draw = layer()
    p = appear(t, 0.1, 0.5)
    text(draw, (66, 40 - (1 - p) * 10), "the brief", path=SERIF_B, size=30)
    text(draw, (68, 82), "one line, four facts, and the questions the gaps imply", size=16, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.25, 0.7)
    box = (60, 122, 648, H - 26)
    draw.rounded_rectangle(box, radius=14, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = ken_burns(Image.open(BRIEF_PNG).convert("RGB"), min(1.0, t / 17.0))
    thumb = fit(shot, box[2] - box[0] - 14, box[3] - box[1] - 14)
    # Paste onto the same layer as the frame, so compositing order cannot hide it.
    canvas.paste(
        thumb,
        (
            int(box[0] + (box[2] - box[0] - thumb.width) // 2),
            int(box[1] + (box[3] - box[1] - thumb.height) // 2),
        ),
    )
    stamp(image, canvas, p)

    callouts = [
        ("ONE LINE", "from the page's own meta description"),
        ("FACTS", f"founded {data['founded']}   ·   hq {data['hq']}"),
        ("DATES", "publication where stated, retrieval otherwise"),
        ("QUESTIONS", "derived from what is missing"),
    ]
    y = 132
    for index, (label, detail) in enumerate(callouts):
        p = appear(t, 1.1 + index * 1.5, 0.5)
        if p <= 0:
            y += 116
            continue
        canvas, draw = layer()
        dx = (1 - p) * 40
        panel(draw, (700, y + dx, W - 60, y + 96 + dx), fill=(26, 30, 43))
        text(draw, (722, y + 16 + dx), label, path=UI_B, size=12, fill=ACCENT)
        for line in wrap(detail, font(UI, 16), W - 60 - 744)[:2]:
            text(draw, (722, y + 42 + dx), line, size=16, fill=INK)
        stamp(image, canvas, p)
        y += 116

    canvas, draw = layer()
    p = appear(t, 8.0, 0.5)
    text(draw, (W - 66 - 268, 62), "screenshot of the HTML this run wrote", path=MONO, size=13, fill=DIM)
    stamp(image, canvas, p)
    return image


def scene_series(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 11.5)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.5)
    text(draw, (66, 42 - (1 - p) * 8), "One page, three years, no contradiction", path=SERIF_B, size=30)
    text(draw, (68, 84), "Three headcounts from the same source. That is a timeline, not a disagreement.", size=16, fill=MUTED)
    stamp(image, canvas, p)

    cards = data["employees"][:3]
    width = (W - 132 - 80) // 3
    x = 66
    for index, card in enumerate(cards):
        p = back_out((t - 0.35 - index * 0.7) / 0.55)
        if p <= 0:
            x += width + 40
            continue
        canvas, draw = layer()
        dy = (1 - p) * 26
        box = (x, 128 + dy, x + width, 448 + dy)
        panel(draw, box, fill=(24, 28, 40))
        text(draw, (x + 22, 150 + dy), card["value"], path=SERIF_B, size=44)
        text(draw, (x + 24, 208 + dy), "UNCONFIRMED", path=MONO_B, size=12, fill=AMBER)
        yy = 244 + dy
        for line in wrap(f'"{card["quote"]}"', font(SERIF, 14), width - 46)[:5]:
            text(draw, (x + 22, yy), line, path=SERIF, size=14, fill=(198, 204, 218))
            yy += 21
        stamp(image, canvas, min(1.0, p + 0.2))
        x += width + 40

    canvas, draw = layer()
    p = appear(t, 3.0, 0.5)
    text(draw, (66, 486), "conflicting values only count as contested when two different sources disagree.", size=17, fill=INK)
    text(draw, (66, 518), "one page giving a series is filed as unconfirmed, with the quotes kept.", size=17, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 4.2, 0.5)
    text(draw, (66, 574), "it does not manufacture a fight to look clever", path=MONO_B, size=17, fill=AMBER)
    stamp(image, canvas, p)
    return image


def scene_pdf(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 7.5)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.5)
    text(draw, (66, 38 - (1 - p) * 8), "A4 PDF, rendered by the plugin", path=SERIF_B, size=30)
    text(draw, (68, 80), "no WeasyPrint, no reportlab, no typst. The writer is in the repo.", size=16, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.2, 0.6)
    lift = (1 - p) * 24
    box = (66, 116 + lift, 452, H - 26 + lift)
    draw.rounded_rectangle(box, radius=12, fill=(247, 247, 250), outline=(70, 78, 98), width=2)
    shot = fit(Image.open(PDF_PNG).convert("RGB"), box[2] - box[0] - 12, box[3] - box[1] - 12)
    canvas.paste(shot, (int(box[0]) + 6, int(box[1]) + 6))
    stamp(image, canvas, p)

    lines = ["base-14 Helvetica", "word wrap and pagination", "numbered source appendix", "a policy line in the footer"]
    y = 150
    for index, line in enumerate(lines):
        p = appear(t, 0.9 + index * 0.35, 0.45)
        canvas, draw = layer()
        draw.rectangle([502, int(y + 6), 506, int(y + 22)], fill=ACCENT)
        text(draw, (520, y), line, size=19)
        stamp(image, canvas, p)
        y += 44

    canvas, draw = layer()
    p = appear(t, 2.9, 0.5)
    text(draw, (502, y + 16), "written in the same run as the HTML", path=MONO, size=14, fill=DIM)
    stamp(image, canvas, p)
    return image


def scene_diff(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 9.5)
    canvas, draw = layer()
    p = appear(t, 0.05, 0.5)
    text(draw, (66, 42 - (1 - p) * 8), "The second look", path=SERIF_B, size=30)
    text(draw, (68, 84), "Refresh ran again against the same six documents.", size=16, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.15, 0.5)
    panel(draw, (66, 126, W - 66, 402), fill=(21, 25, 36))
    text(draw, (96, 150), "DIFF AGAINST THE PREVIOUS SNAPSHOT", path=UI_B, size=12, fill=ACCENT)
    draw.line([96, 176, W - 96, 176], fill=(48, 54, 72))
    stamp(image, canvas, p)

    p = back_out((t - 0.5) / 0.7)
    if p > 0:
        canvas, draw = layer()
        pulse = 1.0 + 0.04 * math_sin(t * 3.0)
        size = int(76 * p * pulse)
        text(draw, (98, 214 + (1 - p) * 20), str(data["diff_changes"]), path=SERIF_B, size=size, fill=MINT)
        stamp(image, canvas, min(1.0, p))

    canvas, draw = layer()
    p = appear(t, 1.3, 0.5)
    text(draw, (196, 250), "changes", path=SERIF, size=30, fill=MUTED)
    text(draw, (98, 330), "Nothing changed between the two snapshots, and it says so.", size=18, fill=INK)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 2.6, 0.5)
    text(draw, (66, 452), "A dossier that invents activity to look busy is worse than one that stays quiet.", size=17, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 3.6, 0.5)
    text(draw, (66, 506), "when something does move, only that appears:  + ceo,  - ceo,  nothing else",
         path=MONO_B, size=16, fill=AMBER)
    stamp(image, canvas, p)
    return image


def scene_close(t: float, data: dict) -> Image.Image:
    image = drift(frame(), t, 8.5)
    canvas, draw = layer()
    p = appear(t, 0.1, 0.6)
    draw.rectangle([0, 0, W, 4], fill=ACCENT)
    text(draw, (88, 120 - (1 - p) * 16), "Dossier", path=SERIF_B, size=70)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 0.45, 0.5)
    text(draw, (92, 210), "sourced   ·   dated   ·   refreshable", path=SERIF, size=28, fill=MUTED)
    stamp(image, canvas, p)

    lines = [
        "hermes plugins install dossier",
        "/dossier Valve Corporation",
        "A4 PDF  ·  HTML  ·  Desktop page  ·  cron blueprint",
    ]
    y = 300
    for index, line in enumerate(lines):
        p = appear(t, 0.9 + index * 0.4, 0.4)
        canvas, draw = layer()
        text(draw, (92, y), line, path=MONO, size=19, fill=INK if index == 0 else MUTED)
        stamp(image, canvas, p)
        y += 40

    canvas, draw = layer()
    p = appear(t, 2.6, 0.5)
    text(draw, (92, 470), "97 tests   ·   doctor and validate clean   ·   MIT   ·   requires Hermes >= 0.23",
         size=16, fill=MUTED)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 3.2, 0.6)
    text(draw, (92, 528), "github.com/Frazzlesprite/dossier-plugin", path=MONO_B, size=21, fill=ACCENT)
    stamp(image, canvas, p)

    canvas, draw = layer()
    p = appear(t, 4.0, 0.5)
    text(draw, (92, 572), f"sources captured {data['captured']}, replayed for this recording",
         path=MONO, size=13, fill=DIM)
    stamp(image, canvas, p)
    return image


SCENE_FUNCS = {
    "title": scene_title,
    "command": scene_command,
    "sources": scene_sources,
    "brief": scene_brief,
    "series": scene_series,
    "pdf": scene_pdf,
    "diff": scene_diff,
    "close": scene_close,
}


def render_silent(data: dict, target: Path) -> Path:
    writer = imageio_ffmpeg.write_frames(
        str(target), (W, H), fps=FPS, codec="libx264",
        output_params=["-crf", "19", "-pix_fmt", "yuv420p"],
    )
    writer.send(None)
    elapsed = 0.0
    for name, duration in SCENES:
        func = SCENE_FUNCS[name]
        frames = int(duration * FPS)
        for index in range(frames):
            t = index / FPS
            image = func(t, data)
            progress(image, elapsed + t, TOTAL)
            edge = min(t, duration - t)
            alpha = 1.0 if edge >= 0.22 else edge / 0.22
            if alpha < 1.0:
                image = Image.blend(Image.new("RGB", (W, H), (5, 6, 10)), image, alpha)
            writer.send(image.tobytes())
        elapsed += duration
    writer.close()
    return target


def main() -> Path:
    if not BRIEF_PNG.exists() or not PDF_PNG.exists():
        raise SystemExit(f"screenshots missing in {SHOTS}")
    data = collect()

    build_dir = Path(tempfile.gettempdir()) / "opencode"
    build_dir.mkdir(parents=True, exist_ok=True)
    silent = build_dir / "valve-silent.mp4"

    print("rendering frames...")
    render_silent(data, silent)

    print("synthesising audio...")
    audio = make_audio.build(TOTAL, SCENES, build_dir / "valve-audio.wav")

    print("muxing...")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", str(silent), "-i", str(audio),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(OUT),
        ],
        check=True,
    )
    print(f"wrote {OUT} ({TOTAL:.1f}s, {FPS}fps, with audio)")
    return OUT


if __name__ == "__main__":
    main()
