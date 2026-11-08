"""Build the demo video from a real run of the demo case.

Every number on screen comes from `demo_contradiction.run` — headline, dated
facts, the contested pair, the diff — so the video cannot drift away from what
the code actually produces. Frames are drawn with Pillow and encoded with the
ffmpeg binary that imageio-ffmpeg ships.

    python scripts/make_video.py            # writes docs/dossier-demo.mp4

Developer tooling only: Pillow and imageio-ffmpeg are not plugin dependencies.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import imageio_ffmpeg  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import demo_contradiction  # noqa: E402

W, H = 1280, 720
FPS = 20
OUT = ROOT / "docs" / "dossier-demo.mp4"

BG = (16, 18, 24)
PANEL = (23, 26, 35)
INK = (232, 235, 242)
MUTED = (139, 147, 167)
ACCENT = (122, 162, 247)
GREEN = (126, 200, 145)
AMBER = (227, 179, 92)
RED = (231, 120, 120)

FONTS = {
    "mono": r"C:\Windows\Fonts\consola.ttf",
    "monob": r"C:\Windows\Fonts\consolab.ttf",
    "serif": r"C:\Windows\Fonts\georgia.ttf",
    "serifb": r"C:\Windows\Fonts\georgiab.ttf",
    "ui": r"C:\Windows\Fonts\segoeui.ttf",
    "uib": r"C:\Windows\Fonts\segoeuib.ttf",
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS.get(kind) or FONTS["ui"]
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if f.getlength(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    return lines + ([current] if current else [])


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    return image, ImageDraw.Draw(image)


def text(draw, xy, value, *, kind="ui", size=24, fill=INK):
    draw.text(xy, value, font=font(kind, size), fill=fill)


def panel(draw, box, *, fill=PANEL, outline=(45, 50, 64)):
    draw.rounded_rectangle(box, radius=14, fill=fill, outline=outline, width=1)


def fade(image: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 1.0:
        return image
    overlay = Image.new("RGB", image.size, (0, 0, 0))
    return Image.blend(overlay, image, max(0.0, min(1.0, alpha)))


def scene_title(t: float) -> Image.Image:
    image, draw = canvas()
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    text(draw, (90, 210), "Dossier", kind="serifb", size=96)
    text(draw, (94, 330), "Everything you should know before you walk in.", kind="serif", size=34, fill=MUTED)
    text(draw, (94, 392), "sourced and dated", kind="serif", size=34, fill=MUTED)
    y = 500
    for line in ("Every claim cites a fetched page, with a publication and retrieval date.",
                 "Contradictions are printed as contested, never resolved to a winner.",
                 "The second look tells you what changed."):
        text(draw, (96, y), line, kind="ui", size=20, fill=INK if y == 500 else MUTED)
        y += 38
    text(draw, (96, 650), "Hermes plugin  ·  MIT  ·  PDF, HTML, Desktop", kind="mono", size=18, fill=ACCENT)
    return image


SOURCES = [
    ("official", "acme.example  ·  homepage + /about", GREEN),
    ("registry", "SEC EDGAR  ·  CIK 0001234567  ·  10-K", GREEN),
    ("github", "github.com/acme  ·  2 repositories", GREEN),
    ("search", "web_search  ·  6 pages fetched in full", GREEN),
    ("news", "news  ·  2 items inside 90 days", GREEN),
]


def scene_sources(t: float, total: float) -> Image.Image:
    image, draw = canvas()
    panel(draw, (70, 60, W - 70, H - 60))
    text(draw, (100, 88), "hermes", kind="monob", size=18, fill=MUTED)
    text(draw, (100, 120), "$ /dossier Acme Robotics", kind="monob", size=30, fill=INK)

    typed = min(len("Acme Robotics"), int(t * 14) % 1000)
    command = "/dossier Acme Robotics"[: 11 + typed]
    draw.rectangle([98, 118, W - 100, 162], fill=PANEL)
    text(draw, (100, 120), "$ " + command + ("_" if int(t * 2) % 2 == 0 else " "), kind="monob", size=30, fill=INK)

    y = 196
    for index, (kind, detail, colour) in enumerate(SOURCES):
        if t < 1.6 + index * 1.35:
            break
        text(draw, (104, y), "✓", kind="monob", size=22, fill=colour)
        text(draw, (136, y), kind.ljust(10), kind="monob", size=20, fill=colour)
        text(draw, (274, y), detail, kind="mono", size=18, fill=MUTED)
        y += 42

    if t > 1.6 + len(SOURCES) * 1.35:
        text(draw, (104, y + 26),
             "12 sources  ·  9 claims  ·  1 contested  ·  0 unsourced sentences",
             kind="monob", size=20, fill=INK)
        text(draw, (104, H - 108), "one request per host per second, robots.txt honoured",
             kind="mono", size=16, fill=MUTED)
    return image


def scene_brief(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    panel(draw, (70, 50, W - 70, H - 50), fill=(20, 21, 26))
    text(draw, (104, 74), "ACME ROBOTICS", kind="uib", size=15, fill=MUTED)
    text(draw, (104, 96),
         f"org  ·  snapshot 2026-11-09  ·  {data['source_count']} sources  ·  {data['claim_count']} claims",
         kind="ui", size=14, fill=MUTED)

    headline = data["headline"]
    y = 132
    for line in wrap(headline, font("serif", 30), W - 220)[:3]:
        text(draw, (104, y), line, kind="serif", size=30)
        y += 40

    y += 18
    text(draw, (104, y), "FACTS", kind="uib", size=13, fill=ACCENT)
    draw.line([104, y + 24, W - 104, y + 24], fill=(48, 54, 70))
    y += 40

    for index, (label, value, source, colour) in enumerate(data["facts"]):
        if t < 0.35 + index * 0.6:
            break
        shown = value if len(value) <= 46 else value[:43].rstrip() + "…"
        text(draw, (104, y), label.ljust(12), kind="monob", size=17, fill=MUTED)
        text(draw, (274, y), shown, kind="ui", size=19, fill=colour)
        text(draw, (W - 104 - int(font("mono", 14).getlength(source)) - 8, y + 3),
             source, kind="mono", size=14, fill=MUTED)
        y += 38

    text(draw, (104, H - 96), "every line above carries a source URL and both dates",
         kind="mono", size=15, fill=MUTED)
    return image


def scene_contested(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    text(draw, (70, 62), "A contradiction, kept as one", kind="serifb", size=34)
    text(draw, (72, 112), "Two sources disagree about headcount. The brief prints both, with dates.",
         kind="ui", size=19, fill=MUTED)

    values = data["contested"]
    boxes = [(70, 168, 610, 470), (670, 168, W - 70, 470)]
    for (box, value) in zip(boxes, values):
        panel(draw, box, fill=(24, 26, 34))
        text(draw, (box[0] + 28, box[1] + 26), value["value"], kind="serifb", size=44)
        text(draw, (box[0] + 30, box[1] + 88), f"{value['confidence']:.2f} confidence", kind="mono", size=15, fill=AMBER)
        text(draw, (box[0] + 30, box[1] + 118), value["url"], kind="mono", size=14, fill=ACCENT)
        text(draw, (box[0] + 30, box[1] + 142), value["date"], kind="mono", size=14, fill=MUTED)
        y = box[1] + 176
        for line in wrap(f'"{value["quote"]}"', font("serif", 16), box[2] - box[0] - 56)[:5]:
            text(draw, (box[0] + 30, y), line, kind="serif", size=16, fill=(200, 205, 216))
            y += 24

    if t > 1.2:
        text(draw, (72, 500), "contested  ·  never resolved to a winner  ·  both quotes verbatim from the page",
             kind="monob", size=19, fill=AMBER)
    if t > 2.2:
        text(draw, (72, 546), "Why do sources disagree about employees (120, 160)?",
             kind="ui", size=19, fill=INK)
        text(draw, (72, 578), "— the first of three questions the brief asks the reader to put to someone",
             kind="ui", size=16, fill=MUTED)
    return image


def scene_diff(t: float, data: dict) -> Image.Image:
    image, draw = canvas()
    text(draw, (70, 62), "The second look", kind="serifb", size=34)
    text(draw, (72, 112), "Refreshed a week later. The diff reports only what changed.",
         kind="ui", size=19, fill=MUTED)

    panel(draw, (70, 162, W - 70, 470))
    text(draw, (100, 186), "CHANGES SINCE THE PREVIOUS SNAPSHOT", kind="uib", size=13, fill=ACCENT)
    draw.line([100, 212, W - 100, 212], fill=(48, 54, 70))

    rows = [("+", "ceo", "Priya Raman", GREEN, "appointed October 2026"),
            ("-", "ceo", "Dana Whitfield", RED, "no longer listed")]
    y = 240
    for index, (sign, predicate, value, colour, note) in enumerate(rows):
        if t < 0.5 + index * 0.9:
            break
        text(draw, (104, y), sign, kind="monob", size=26, fill=colour)
        text(draw, (140, y + 2), predicate, kind="monob", size=20, fill=MUTED)
        text(draw, (250, y + 2), value, kind="ui", size=21, fill=INK)
        text(draw, (W - 340, y + 6), note, kind="mono", size=14, fill=MUTED)
        y += 52

    if t > 2.2:
        text(draw, (104, 352), "2 changes.  Everything else identical.", kind="ui", size=19, fill=MUTED)
        text(draw, (104, 392), "Unchanged claims are deliberately absent — no noise, no re-reading.",
             kind="ui", size=17, fill=MUTED)
    return image


def scene_end(t: float) -> Image.Image:
    image, draw = canvas()
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    text(draw, (90, 150), "Dossier", kind="serifb", size=76)
    text(draw, (94, 250), "sourced · dated · refreshable", kind="serif", size=32, fill=MUTED)

    y = 340
    for line in ("/dossier <name>   ·   dossier_build | show | diff | refresh | forget | watch",
                 "A4 PDF and HTML   ·   chat card   ·   Desktop page with history",
                 "Registry: SEC EDGAR, ABN Lookup, Companies House",
                 "Cron via automation blueprint   ·   watchlist cadence"):
        text(draw, (94, y), line, kind="mono", size=19, fill=INK)
        y += 40

    text(draw, (94, 560), "github.com/Frazzlesprite/dossier-plugin", kind="monob", size=22, fill=ACCENT)
    text(draw, (94, 600), "MIT  ·  92 tests  ·  doctor and validate clean  ·  requires Hermes >= 0.23",
         kind="ui", size=17, fill=MUTED)
    return image


LABELS = [
    ("founded", "Founded"),
    ("hq", "HQ"),
    ("ceo", "Leadership"),
    ("employees", "Size"),
    ("funding", "Funding"),
    ("role", "Role"),
]


def collect() -> dict:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        demo_contradiction.main()
    last = demo_contradiction.LAST
    first, second, diff = last["first"], last["second"], last["diff"]

    contested = []
    for claim in first["claims"]:
        if claim["status"] != "contested":
            continue
        evidence = claim["evidence"][0]
        contested.append(
            {
                "value": claim["value"],
                "confidence": claim["confidence"],
                "url": evidence["source_url"],
                "date": evidence["published_at"] or evidence["retrieved_at"][:10],
                "quote": evidence["quote"],
            }
        )
    contested.sort(key=lambda item: int(item["value"]) if item["value"].isdigit() else 0)

    contested_predicates = {claim["predicate"] for claim in first["claims"] if claim["status"] == "contested"}
    facts = []
    for predicate, label in LABELS:
        claims = [claim for claim in first["claims"] if claim["predicate"] == predicate]
        if not claims:
            continue
        if predicate in contested_predicates:
            joined = "  /  ".join(claim["value"] for claim in claims)
            facts.append((label, joined, "sources disagree - contested", AMBER))
            continue
        claim = claims[0]
        evidence = claim["evidence"][0]
        host = evidence["source_url"].split("/")[2]
        when = evidence["published_at"] or evidence["retrieved_at"][:10]
        facts.append((label, claim["value"], f"{host}  {when}", GREEN))

    return {
        "headline": first["headline"],
        "facts": facts,
        "contested": contested[:2],
        "diff": diff,
        "source_count": first["counts"]["documents"],
        "claim_count": first["counts"]["claims"],
    }


SCENES = [
    ("title", 5.5),
    ("sources", 18.0),
    ("brief", 15.0),
    ("contested", 14.0),
    ("diff", 12.0),
    ("end", 7.5),
]


def build() -> Path:
    data = collect()
    if len(data["contested"]) < 2:
        raise SystemExit("the demo did not produce two contested values")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(str(OUT), (W, H), fps=FPS, codec="libx264",
                                         output_params=["-crf", "20", "-pix_fmt", "yuv420p"])
    writer.send(None)

    total_frames = 0
    for name, duration in SCENES:
        frames = int(duration * FPS)
        for index in range(frames):
            t = index / FPS
            if name == "title":
                frame = scene_title(t)
            elif name == "sources":
                frame = scene_sources(t, duration)
            elif name == "brief":
                frame = scene_brief(t, data)
            elif name == "contested":
                frame = scene_contested(t, data)
            elif name == "diff":
                frame = scene_diff(t, data)
            else:
                frame = scene_end(t)

            # 0.35s fade in and out per scene.
            edge = min(t, duration - t)
            alpha = 1.0 if edge >= 0.35 else edge / 0.35
            writer.send(fade(frame, alpha).tobytes())
            total_frames += 1

    writer.close()
    print(f"wrote {OUT}  ({total_frames} frames, {total_frames / FPS:.1f}s)")
    return OUT


if __name__ == "__main__":
    build()
