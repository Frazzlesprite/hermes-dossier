"""Rendering: an A4 document and a chat card.

HTML is the canonical output. Print-to-PDF from the Desktop or a browser gives
the two-page A4 file without adding a typesetting dependency; the stylesheet
sets `@page` and page breaks so it lands on two pages. There is no separate PDF
writer, and the README says so.
"""

from __future__ import annotations

import html
import re

from .models import Brief, Section

POLICY_FOOTER = (
    "Built from public sources only. No inference of health, religion, sexuality, "
    "politics, ethnicity or union membership. Delete with /dossier forget &lt;name&gt;."
)

_CSS = """
@page { size: A4; margin: 16mm 15mm; }
:root { --ink:#14161a; --muted:#5b6270; --rule:#d8dbe2; --accent:#1f4b8f; --warn:#8a3b12; }
* { box-sizing: border-box; }
body { margin:0; color:var(--ink); background:#f4f5f7;
  font: 10.5pt/1.45 "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }
.page { width:210mm; min-height:297mm; margin:0 auto; background:#fff; padding:16mm 15mm; }
.brief + .brief { break-before: page; page-break-before: always; }
h1 { font-size:19pt; line-height:1.15; margin:0 0 2mm; letter-spacing:-0.01em; }
.meta { color:var(--muted); font-size:8.5pt; font-family: ui-sans-serif, system-ui, sans-serif;
  text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6mm; }
h2 { font-size:9pt; font-family: ui-sans-serif, system-ui, sans-serif; text-transform:uppercase;
  letter-spacing:0.12em; color:var(--accent); margin:6mm 0 1.5mm; border-bottom:1px solid var(--rule);
  padding-bottom:1mm; }
ul { margin:0; padding-left:5mm; }
li { margin:0 0 1.2mm; }
li::marker { color:var(--muted); }
p.note { margin:0; color:var(--muted); }
.facts li, .recent li { list-style:disc; }
.contested li { color:var(--warn); }
footer { margin-top:8mm; border-top:1px solid var(--rule); padding-top:2mm;
  color:var(--muted); font-size:7.5pt; font-family: ui-sans-serif, system-ui, sans-serif; }
ol.src { font-size:8pt; font-family: ui-sans-serif, system-ui, sans-serif; color:var(--muted);
  padding-left:6mm; word-break:break-all; }
ol.src li { margin-bottom:0.8mm; }
@media print { body { background:#fff; } .page { width:auto; min-height:0; margin:0; padding:0; } }
"""


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _section(section: Section) -> str:
    parts = [f'<h2>{html.escape(section.title)}</h2>']
    if section.bullets:
        items = "".join(f"<li>{_inline(b.text)}</li>" for b in section.bullets)
        parts.append(f'<ul class="{section.id}">{items}</ul>')
    elif section.note:
        parts.append(f'<p class="note">{_inline(section.note)}</p>')
    if section.bullets and section.note:
        parts.append(f'<p class="note">{_inline(section.note)}</p>')
    return "\n".join(parts)


def render_html(brief: Brief, *, title: str = "Dossier") -> str:
    entity = brief.entity
    name = html.escape(str(entity.get("canonical_name") or "Dossier"))
    kind = html.escape(str(entity.get("kind") or "org"))
    generated = html.escape(brief.generated_at)

    body = "\n".join(_section(s) for s in brief.sections if s.id != "sources")
    sources = "".join(
        f'<li>{html.escape(e.source_url)}, {html.escape(e.published_at or "undated")}, '
        f"retrieved {html.escape(e.retrieved_at[:10])}</li>"
        for e in brief.sources
    )
    notes = ""
    if brief.notes:
        notes = '<h2>Adapter notes</h2><ul class="src">' + "".join(
            f"<li>{_inline(n)}</li>" for n in brief.notes
        ) + "</ul>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{name}: {html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{_CSS}</style></head>
<body><div class="page brief">
<h1>{name}</h1>
<div class="meta">{kind} · brief generated {generated} · {len(brief.sources)} source(s)</div>
{body}
<footer>{POLICY_FOOTER}</footer>
</div>
<div class="page appendix">
<h1>Sources</h1>
<div class="meta">Every claim above cites one of these. Dates are publication dates where the page states one, else retrieval dates.</div>
<ol class="src">{sources}</ol>
{notes}
<footer>{POLICY_FOOTER}</footer>
</div></body></html>"""


def render_pdf(brief: Brief) -> bytes:
    """The A4 PDF, from the same Brief object as the HTML."""
    from .pdf import render_pdf as _build  # local import keeps pdf.py importable alone

    return _build(brief)


def render_card(brief: Brief, *, href: str | None = None) -> str:
    """The chat card: one line, three questions, a link. Nothing else."""
    name = str(brief.entity.get("canonical_name") or "Dossier")
    lines = [f"**{name}**", brief.headline]
    if brief.questions:
        lines.append("")
        lines.append("**Ask:**")
        lines.extend(f"{i}. {q}" for i, q in enumerate(brief.questions, start=1))
    if href:
        lines.append("")
        lines.append(f"Full brief: {href}")
    return "\n".join(lines)
