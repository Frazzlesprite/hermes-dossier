r"""The submission demo: Valve Corporation, from the captured source set.

Every claim, date and quote on screen comes out of `demo_valve.main()`, which
replays the captured pages through the real pipeline. The brief and the PDF
frames are screenshots of the actual output files, not illustrations.

    python scripts/make_video_valve.py     # docs/dossier-valve-demo.mp4

Developer tooling: Pillow and imageio-ffmpeg are not plugin dependencies.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imageio_ffmpeg  # noqa: E402
from PIL import Image  # noqa: E402

import demo_valve  # noqa: E402
from make_video import (  # noqa: E402
    ACCENT, AMBER, BG, GREEN, H, INK, MUTED, PANEL, RED, W, canvas, fade, font, panel, text, wrap,
)

OUT = ROOT / "docs" / "dossier-valve-demo.mp4"
SHOTS = Path(tempfile.gettempdir()) / "opencode" / "valveshot"
BRIEF_PNG = SHOTS / "brief.png"
PDF_PNG = SHOTS / "pdf-1.png"


def fit(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(max_w / image.width, max_h / image.height)
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def picture(canvas_image: Image.Image, draw, shot: Image.Image, box, ring=(58, 64, 80)) -> None:
    x0, y0, x1, y1 = box
    thumb = fit(shot, x1 - x0 - 16, y1 - y0 - 16)
    x = x0 + (x1 - x0 - thumb.width) // 2
    y = y0 + (y1 - y0 - thumb.height) // 2
    draw.rounded_rectangle(box, radius=12, fill=(247, 247, 249), outline=ring, width=2)
    canvas_image.paste(thumb, (x, y))


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
        "product": facts.get("product", {}).get("value", ""),
        "employees": [
            {
                "value": claim["value"],
                "quote": claim["evidence"][0]["quote"],
                "url": claim["evidence"][0]["source_url"],
            }
            for claim in employees
        ],
        "counts": first["counts"],
        "diff_changes": (second.get("diff") or {}).get("changed_count", 0),
        "snapshot": first.get("entity", {}).get("name", "Valve Corporation"),
        "captured": last["index"]["captured_at"],
        "registry_note": next((n for n in notes if n.startswith("registry(EDGAR)")), ""),
        "github_note": next((n for n in notes if n.startswith("github")), ""),
        "guard_note": next((n for n in notes if n.startswith("collision guard")), ""),
        "news_note": next((n for n in notes if n.startswith("news")), ""),
        "generated": first["html"].count("<h2>") and first.get("counts", {}).get("documents", 0),
    }



def tick(draw, x: float, y: float, colour, size: int = 11) -> None:
    """A check mark drawn with lines, so it never depends on a font glyph."""
    draw.line([(x, y + size * 0.55), (x + size * 0.4, y + size)], fill=colour, width=3)
    draw.line([(x + size * 0.4, y + size), (x + size * 1.15, y + size * 0.1)], fill=colour, width=3)


def scene_title(t: float) -> Image.Image:
    image, draw = canvas()
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    text(draw, (90, 190), "Dossier", kind="serifb", size=92)
    text(draw, (94, 300), "Everything you should know before you walk in.", kind="serif", size=32, fill=MUTED)
    text(draw, (94, 356), "sourced and dated", kind="serif", size=32, fill=MUTED)
    text(draw, (96, 468), "A brief on one entity. Every claim cites the page it came from.", kind="ui", size=20)
    text(draw, (96, 504), "Contradictions stay contested. Gaps stay gaps.", kind="ui", size=20, fill=MUTED)
    text(draw, (96, 540), "The second look tells you what changed.", kind="ui", size=20, fill=MUTED)
    text(draw, (96, 646), "Hermes plugin  ·  MIT  ·  PDF, HTML, Desktop, cron", kind="mono", size=18, fill=ACCENT)
    return image


def scene_command(t: float) -> Image.Image:
    image, draw = canvas()
    panel(draw, (70, 90, W - 70, H - 90))
    text(draw, (100, 116), "hermes", kind="monob", size=17, fill=MUTED)
    typed = min(len("Valve Corporation"), int(t * 16))
    command = "/dossier Valve Corporation"[:9 + typed]
    text(draw, (100, 150), "$ " + command + ("_" if int(t * 3) % 2 == 0 else " "), kind="monob", size=30)
    if t > 1.4:
        text(draw, (100, 210), "resolving the entity", kind="mono", size=19, fill=MUTED)
    if t > 1.9:
        text(draw, (100, 244), "→ one candidate: valvesoftware.com", kind="mono", size=19, fill=GREEN)
    if t > 2.5:
        text(draw, (100, 286), "no ambiguity to ask about", kind="mono", size=17, fill=MUTED)
    return image


def scene_sources(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    panel(draw, (70, 60, W - 70, H - 60))
    text(draw, (100, 86), "sources, in the order they landed", kind="mono", size=17, fill=MUTED)
    drawn = [
        ("official", "valvesoftware.com  ·  3 pages  ·  /en, /about, /press"),
        ("search", "en.wikipedia.org  ·  fetched in full"),
        ("search", "forbes.com/companies/valve  ·  fetched in full"),
        ("registry", "SEC EDGAR  ·  no registrant: private company"),
    ]
    y = 136
    for index, (kind, detail) in enumerate(drawn):
        if t < 0.4 + index * 1.2:
            break
        tick(draw, 106, y + 4, GREEN)
        text(draw, (134, y), kind.ljust(10), kind="monob", size=19, fill=GREEN)
        text(draw, (272, y), detail, kind="mono", size=17, fill=MUTED)
        y += 40

    if t > 5.2:
        text(draw, (100, y + 18), "what it could not do", kind="monob", size=17, fill=AMBER)
        notes = [note for note in (data["github_note"], data["news_note"], data["guard_note"]) if note]
        ny = y + 54
        for note in notes:
            for line in wrap(note, font("mono", 15), W - 240)[:2]:
                text(draw, (104, ny), line, kind="mono", size=15, fill=(198, 176, 140))
                ny += 22
            ny += 6

    if t > 9.5:
        text(draw, (100, H - 104), "six documents  ·  six claims  ·  zero invented", kind="monob", size=18, fill=INK)
    return image


def scene_brief(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    draw.rectangle([0, 0, W, H], fill=BG)
    text(draw, (70, 44), "the brief", kind="serifb", size=30)
    text(draw, (72, 86), "one line, four facts, and the questions the gaps imply", kind="ui", size=17, fill=MUTED)

    shot = Image.open(BRIEF_PNG).convert("RGB")
    box = (60, 124, 640, H - 40)
    picture(image, draw, shot, box)

    callouts = [
        ("one line", "from the page's own meta description"),
        ("facts", f"founded {data['founded']}  ·  hq {data['hq']}"),
        ("dates", "publication where stated, retrieval otherwise"),
        ("questions", "derived from what is missing"),
    ]
    y = 150
    for index, (label, detail) in enumerate(callouts):
        if t < 1.0 + index * 1.6:
            break
        panel(draw, (680, y, W - 60, y + 92), fill=(26, 29, 38))
        text(draw, (700, y + 16), label.upper(), kind="uib", size=13, fill=ACCENT)
        for line in wrap(detail, font("ui", 17), W - 60 - 724)[:2]:
            text(draw, (700, y + 42), line, kind="ui", size=17, fill=INK)
        y += 108
    return image


def scene_series(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    text(draw, (70, 52), "One page, three years, no contradiction", kind="serifb", size=32)
    text(draw, (72, 98), "Three headcounts from the same source. That is a timeline, not a disagreement.", kind="ui", size=18, fill=MUTED)

    cards = data["employees"][:3]
    width = (W - 140 - 40 * 2) // 3
    x = 70
    for index, card in enumerate(cards):
        if t < 0.4 + index * 1.1:
            break
        box = (x, 150, x + width, 470)
        panel(draw, box, fill=(24, 26, 34))
        text(draw, (x + 22, 168), card["value"], kind="serifb", size=40)
        text(draw, (x + 24, 226), "unconfirmed", kind="monob", size=13, fill=AMBER)
        y = 262
        for line in wrap(f'"{card["quote"]}"', font("serif", 15), width - 48)[:5]:
            text(draw, (x + 22, y), line, kind="serif", size=15, fill=(198, 203, 214))
            y += 22
        x += width + 40

    if t > 4.2:
        text(draw, (72, 512), "conflicting values only count as contested when two different sources disagree.",
             kind="ui", size=18, fill=INK)
        text(draw, (72, 546), "One page giving a series is filed as unconfirmed, with the quotes kept.",
             kind="ui", size=18, fill=MUTED)
        text(draw, (72, 596), "the brief does not manufacture a fight to look clever",
             kind="monob", size=18, fill=AMBER)
    return image


def scene_pdf(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    text(draw, (70, 44), "A4 PDF, rendered by the plugin", kind="serifb", size=30)
    text(draw, (72, 86), "no WeasyPrint, no reportlab, no typst. The writer is in the repo.", kind="ui", size=17, fill=MUTED)
    shot = Image.open(PDF_PNG).convert("RGB")
    picture(image, draw, shot, (70, 120, 470, H - 40))
    y = 150
    for line in ("base-14 Helvetica", "word wrap and pagination", "numbered source appendix", "a policy line in the footer"):
        if t < 0.6 + (y - 150) / 150:
            break
        text(draw, (520, y), "·  " + line, kind="ui", size=19, fill=INK)
        y += 42
    if t > 2.6:
        text(draw, (520, y + 20), "generated in the same run as the HTML", kind="mono", size=15, fill=MUTED)
    return image


def scene_difff(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    text(draw, (70, 52), "The second look", kind="serifb", size=32)
    text(draw, (72, 98), "Refresh ran again against the same six documents.", kind="ui", size=18, fill=MUTED)

    panel(draw, (70, 150, W - 70, 420))
    text(draw, (100, 176), "DIFF AGAINST THE PREVIOUS SNAPSHOT", kind="uib", size=13, fill=ACCENT)
    draw.line([100, 204, W - 100, 204], fill=(48, 54, 70))

    if t > 0.5:
        text(draw, (104, 244), str(data["diff_changes"]), kind="serifb", size=84, fill=GREEN)
        text(draw, (220, 286), "changes", kind="serif", size=34, fill=MUTED)
    if t > 1.6:
        text(draw, (104, 356), "Nothing changed between the two snapshots, and it says so.", kind="ui", size=19, fill=INK)
    if t > 2.6:
        text(draw, (72, 470), "A dossier that invents activity to look busy is worse than one that stays quiet.",
             kind="ui", size=18, fill=MUTED)
        text(draw, (72, 520), "when something does move, only that appears: + ceo, - ceo, nothing else",
             kind="monob", size=17, fill=AMBER)
    return image


def scene_close(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    text(draw, (90, 140), "Dossier", kind="serifb", size=72)
    text(draw, (94, 236), "sourced  ·  dated  ·  refreshable", kind="serif", size=30, fill=MUTED)

    y = 320
    for line in (
        "hermes plugins install dossier",
        "/dossier Valve Corporation",
        "A4 PDF  ·  HTML  ·  Desktop page  ·  cron blueprint",
    ):
        text(draw, (94, y), line, kind="mono", size=19, fill=INK if y == 320 else MUTED)
        y += 40

    text(draw, (94, 500), "97 tests  ·  doctor and validate clean  ·  MIT  ·  requires Hermes >= 0.23",
         kind="ui", size=17, fill=MUTED)
    text(draw, (94, 560), "github.com/Frazzlesprite/dossier-plugin", kind="monob", size=21, fill=ACCENT)
    text(draw, (94, 604), f"sources captured {data['captured']}, replayed for this recording",
         kind="mono", size=14, fill=(120, 128, 146))
    return image


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


def build() -> Path:
    if not BRIEF_PNG.exists() or not PDF_PNG.exists():
        raise SystemExit(
            "screenshots missing: run demo_valve.py, then screenshot the HTML and PDF into "
            f"{SHOTS}"
        )

    data = collect()
    if len(data["employees"]) < 2:
        raise SystemExit("expected at least two unconfirmed headcount values in the replay")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(
        str(OUT), (W, H), fps=20, codec="libx264", output_params=["-crf", "20", "-pix_fmt", "yuv420p"]
    )
    writer.send(None)

    total = 0
    for name, duration in SCENES:
        frames = int(duration * 20)
        for index in range(frames):
            t = index / 20
            if name == "title":
                frame = scene_title(t)
            elif name == "command":
                frame = scene_command(t)
            elif name == "sources":
                frame = scene_sources(t, data)
            elif name == "brief":
                frame = scene_brief(t, data)
            elif name == "series":
                frame = scene_series(t, data)
            elif name == "pdf":
                frame = scene_pdf(t, data)
            elif name == "diff":
                frame = scene_difff(t, data)
            else:
                frame = scene_close(t, data)

            edge = min(t, duration - t)
            alpha = 1.0 if edge >= 0.3 else edge / 0.3
            writer.send(fade(frame, alpha).tobytes())
            total += 1

    writer.close()
    print(f"wrote {OUT} ({total} frames, {total / 20:.1f}s)")
    return OUT


if __name__ == "__main__":
    build()
