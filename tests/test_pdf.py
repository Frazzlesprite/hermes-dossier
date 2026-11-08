"""The PDF: real file, real pages, real text, no dependencies."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from dossier import pdf as pdf_mod
from dossier.models import Brief, Bullet, Evidence, Section
from dossier.render import render_pdf


def _evidence(url: str = "https://acme.example/about") -> Evidence:
    return Evidence(
        source_url=url,
        source_type="official",
        quote="Acme employs 120 employees.",
        retrieved_at="2026-11-09T00:00:00Z",
        published_at="2026-10-01",
    )


def _brief() -> Brief:
    ev = _evidence()
    return Brief(
        entity={"canonical_name": "Acme Robotics", "kind": "org"},
        headline="Acme Robotics — warehouse robots",
        sections=[
            Section(id="one_line", title="One line", bullets=(Bullet("Acme builds robots [1, 2026-10-01]", (ev,)),)),
            Section(
                id="facts",
                title="Facts",
                bullets=(Bullet("**Size:** 120 employees [1, 2026-10-01]", (ev,)),),
            ),
            Section(id="questions", title="Three questions to ask", note="1. Who runs it?\n2. How big is it?"),
            Section(id="sources", title="Sources"),
        ],
        questions=["Who runs it?"],
        sources=[ev],
        generated_at="2026-11-09T00:00:00Z",
        notes=["search: no backend"],
    )


def test_it_is_a_real_pdf_with_the_brief_inside():
    data = render_pdf(_brief())
    assert data.startswith(b"%PDF-1.")
    reader = PdfReader(BytesIO(data))
    assert len(reader.pages) >= 2, "the source appendix belongs on its own page"

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Acme Robotics" in text
    assert "FACTS" in text
    assert "120 employees" in text
    assert "https://acme.example/about" in text
    assert "Who runs it?" in text


def test_markdown_bold_does_not_leak_into_the_page():
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(render_pdf(_brief()))).pages)
    assert "**" not in text


def test_a_long_brief_paginates():
    ev = _evidence()
    sections = [
        Section(
            id="recent",
            title="Recent",
            bullets=tuple(Bullet(f"Item {i}: " + "a long line of text " * 12, (ev,)) for i in range(40)),
        ),
        Section(id="sources", title="Sources"),
    ]
    brief = Brief(
        entity={"canonical_name": "Long Co", "kind": "org"},
        headline="x",
        sections=sections,
        questions=[],
        sources=[ev],
        generated_at="2026-11-09T00:00:00Z",
    )
    reader = PdfReader(BytesIO(render_pdf(brief)))
    assert len(reader.pages) >= 3


def test_the_writer_is_dependency_free():
    source = pdf_mod.__file__
    assert source.endswith("pdf.py")
    text = open(source, encoding="utf-8").read()
    for forbidden in ("reportlab", "weasyprint", "fpdf", "pypdf"):
        assert f"import {forbidden}" not in text
