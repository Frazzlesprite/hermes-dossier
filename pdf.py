"""A small A4 PDF writer, because the host has no typesetting engine.

Base-14 Helvetica only, no embedded fonts, no dependencies, which means the
PDF is generated everywhere the plugin runs and the catalog has nothing extra to
install or audit.

It is deliberately a writer, not a renderer: the brief is already a list of
sections and bullets, so this lays those out and paginates. Wrapping uses an
average glyph width, which is approximate for proportional type but never
overflows a line beyond its column by more than a few points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Brief

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in points
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 42.5, 45.0, 42.5
BODY = 10.0
LEADING = 14.2
HEAD = 8.6
SMALL = 8.0

FONTS = {"regular": "F1", "bold": "F2", "italic": "F3"}
# Average glyph widths as a fraction of the font size. Helvetica is ~0.52em for
# mixed lowercase, bold a touch wider.
WIDTH_FACTOR = {"regular": 0.50, "bold": 0.54, "italic": 0.49}


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _encode(text: str) -> str:
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _width(text: str, size: float, face: str) -> float:
    return len(text) * size * WIDTH_FACTOR.get(face, 0.5)


def _wrap(text: str, size: float, face: str, width: float) -> list[str]:
    words = re.split(r"(\s+)", text.strip())
    lines: list[str] = []
    current = ""
    for word in words:
        if not word:
            continue
        candidate = current + word
        if _width(candidate.rstrip(), size, face) <= width or not current:
            current = candidate
        else:
            lines.append(current.rstrip())
            current = word.lstrip()
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


@dataclass
class _Page:
    ops: list[str] = field(default_factory=list)


class PdfWriter:
    def __init__(self) -> None:
        self.pages: list[_Page] = []
        self.y = 0.0
        self.page: _Page | None = None

    # -- layout ---------------------------------------------------------
    def new_page(self) -> None:
        self.page = _Page()
        self.pages.append(self.page)
        self.y = PAGE_H - MARGIN_TOP

    def _space(self, amount: float) -> None:
        self.y -= amount
        if self.y < MARGIN_BOTTOM + BODY:
            self.new_page()

    def text(self, x: float, y: float, size: float, face: str, text: str, gray: float = 0.0) -> None:
        assert self.page is not None
        if not text:
            return
        self.page.ops.append(
            f"BT /{FONTS[face]} {size:.2f} Tf {gray:.2f} g {x:.2f} {y:.2f} Td ({_escape(_encode(text))}) Tj ET"
        )

    def rule(self, x1: float, x2: float, y: float, gray: float = 0.78) -> None:
        assert self.page is not None
        self.page.ops.append(f"{gray:.2f} G 0.6 w {x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S")

    def block(self, text: str, *, size: float = BODY, face: str = "regular", width: float | None = None,
              indent: float = 0.0, gray: float = 0.0, leading: float = LEADING) -> None:
        width = width if width is not None else PAGE_W - 2 * MARGIN_X - indent
        for line in _wrap(text, size, face, width):
            self._space(leading)
            self.text(MARGIN_X + indent, self.y, size, face, line, gray)

    def heading(self, text: str) -> None:
        self._space(10.0)
        self.rule(MARGIN_X, PAGE_W - MARGIN_X, self.y + 4.0)
        self._space(HEAD + 4.0)
        self.text(MARGIN_X, self.y, HEAD, "bold", text.upper(), gray=0.15)
        self._space(4.0)

    def bullet(self, text: str) -> None:
        lines = _wrap(text, BODY, "regular", PAGE_W - 2 * MARGIN_X - 12.0)
        for index, line in enumerate(lines):
            self._space(LEADING)
            if index == 0:
                self.text(MARGIN_X + 2.0, self.y, BODY, "regular", "-", gray=0.35)
            self.text(MARGIN_X + 12.0, self.y, BODY, "regular", line)


def _strip_markdown(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")


def render_pdf(brief: Brief) -> bytes:
    writer = PdfWriter()
    writer.new_page()

    name = str(brief.entity.get("canonical_name") or "Dossier")
    kind = str(brief.entity.get("kind") or "org")

    writer.text(MARGIN_X, writer.y, 20.0, "bold", name)
    writer._space(20.0)
    writer.text(
        MARGIN_X, writer.y, SMALL, "regular",
        f"{kind}  |  brief generated {brief.generated_at}  |  {len(brief.sources)} source(s)",
        gray=0.4)
    writer._space(18.0)

    for section in brief.sections:
        if section.id == "sources":
            continue
        writer.heading(section.title)
        if section.bullets:
            for bullet in section.bullets:
                writer.bullet(_strip_markdown(bullet.text))
        elif section.note:
            for line in str(section.note).splitlines():
                writer.block(line, size=9.5, face="italic", gray=0.35, leading=12.6)
        if section.bullets and section.note:
            for line in str(section.note).splitlines():
                writer.block(line, size=9.0, face="italic", gray=0.4, leading=12.0)

    writer._space(14.0)
    writer.rule(MARGIN_X, PAGE_W - MARGIN_X, writer.y + 6.0)
    writer._space(10.0)
    writer.block(
        "Built from public sources only. No inference of health, religion, sexuality, politics, "
        "ethnicity or union membership. Delete with /dossier forget <name>.",
        size=7.2, gray=0.45, leading=9.6)

    # Appendix
    writer.new_page()
    writer.text(MARGIN_X, writer.y, 18.0, "bold", "Sources")
    writer._space(18.0)
    writer.block(
        "Every claim above cites one of these. Dates are publication dates where the page states "
        "one, otherwise retrieval dates.",
        size=8.6, gray=0.4, leading=11.0)
    writer._space(8.0)
    for number, source in enumerate(brief.sources, start=1):
        date = source.published_at or f"retrieved {source.retrieved_at[:10]}"
        writer.block(f"{number}. {source.source_url}  ({date})", size=8.0, gray=0.25, leading=10.6)

    if brief.notes:
        writer.heading("Adapter notes")
        for note in brief.notes:
            writer.bullet(_strip_markdown(str(note)))

    return _emit(writer)


def _emit(writer: PdfWriter) -> bytes:
    objects: list[bytes] = []

    def add(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    font_italic = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>")

    pages_id = len(objects) + 1 + 2 * len(writer.pages)  # reserved below
    page_ids: list[int] = []
    content_ids: list[int] = []

    # Placeholder ordering: [fonts] [page/content pairs] [pages] [catalog]
    for index, page in enumerate(writer.pages, start=1):
        stream = "\n".join(page.ops)
        if index > 1:
            stream += (
                f"\nBT /F1 7.5 Tf 0.45 g {PAGE_W - 2 * MARGIN_X:.2f} {MARGIN_BOTTOM - 12:.2f} Td "
                f"(Page {index} of {len(writer.pages)}) Tj ET"
            )
        content_ids.append(add(f"<< /Length {len(stream.encode('latin-1', 'replace'))} >>\nstream\n{stream}\nendstream".encode("latin-1", "replace")))
        page_ids.append(0)  # filled after we know the Pages id

    pages_id = add(b"")  # placeholder for Pages object
    catalog_id = add(b"")

    # Rewrite the placeholders in place.
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("latin-1")
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")

    for index, content_id in enumerate(content_ids):
        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
            f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R /F3 {font_italic} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        page_ids[index] = add(page_obj.encode("latin-1"))

    # Re-write the Pages placeholder now that page ids exist.
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("latin-1")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + payload + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)
