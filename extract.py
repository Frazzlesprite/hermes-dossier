"""Claim extraction with a hard evidence gate.

Every claim must carry a quote that is a **verbatim substring of the fetched
page text**. That single check is what stops the model, or a bad heuristic, 
from inventing a fact: a claim whose quote cannot be found is rejected, and the
rejection is counted rather than hidden.

Deterministic rules are the backbone, so extraction works in tools, slash
commands and the dashboard backend alike, with no model in the loop. An LLM can
add claims on top, but it passes through exactly the same gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import (
    MAX_QUOTE_CHARS,
    MIN_QUOTE_CHARS,
    PREDICATES,
    SENSITIVE_TERMS,
    ClaimDraft,
    Document,
    Evidence,
    normalise_space)

_BREAK = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z]{3,}")


@dataclass
class ExtractionReport:
    claims: list[ClaimDraft] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def reject(self, predicate: str, reason: str, quote: str = "") -> None:
        self.rejected.append(
            {"predicate": predicate, "reason": reason, "quote": normalise_space(quote)[:200]}
        )


def _sentences(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [s for s in spans if s[1] > s[0]]


QUOTE_PAD_BEFORE = 80
QUOTE_PAD_AFTER = 160
QUOTE_SOFT_MAX = 260


def _quote_for(text: str, spans: list[tuple[int, int]], start: int, end: int) -> str:
    for span_start, span_end in spans:
        if span_start <= start < span_end:
            quote = text[span_start:span_end].strip()
            if len(quote) > QUOTE_SOFT_MAX:
                # Keep a readable window around the matched value instead of a
                # 400-character wall of navigation. Still a verbatim substring.
                low = max(span_start, start - QUOTE_PAD_BEFORE)
                high = min(span_end, end + QUOTE_PAD_AFTER)
                while low < start and text[low - 1] not in " \n":
                    low += 1
                while high < span_end and text[high] not in " \n":
                    high += 1
                quote = text[low:high].strip()
            if len(quote) > MAX_QUOTE_CHARS:
                quote = quote[:MAX_QUOTE_CHARS].rstrip()
            return quote
    return ""


# (predicate, pattern). The value is group 1.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("founded", re.compile(r"\b(?:was\s+)?(?:founded|established|incorporated)\b\s*(?:in\s+)?((?:1[89]|20)\d{2})\b", re.I)),
    ("employees", re.compile(r"\b(\d[\d,]{0,7})\+?\s+(?:employees|staff|people|team members|workers)\b", re.I)),
    # "a team of 40", "employs 120", "workforce of 900": the same claim in the
    # words an About page actually uses, where the number comes first only
    # sometimes.
    ("employees", re.compile(
        r"\b(?:team of|staff of|workforce of|headcount of|employs|employing)\s+"
        r"(?:over\s+|more than\s+|about\s+|around\s+|approximately\s+|roughly\s+)?"
        r"(\d[\d,]{0,7})\b", re.I)),
    # The town alone ("Bellevue") is a weaker fact than the page's own phrasing
    # ("Bellevue, Washington"), and the region only follows when capitalised,
    # so "based in London, which is..." still yields London.
    ("hq", re.compile(r"\b(?i:headquartered|head office is|based|located)\s+in\s+([A-Z][A-Za-z.'\- ]{1,60}(?:,\s*[A-Z][A-Za-z.'\-]{1,30})?)")),
    ("ceo", re.compile(r"\b(?i:CEO|chief executive officer|chief executive|managing director)\b\s*(?:is|was|:|\b)\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})")),
    ("funding", re.compile(r"\b(?:raised|secured|closed|announced)\b[^.$]{0,40}?([$€£]\s?\d[\d.,]*\s?(?:million|billion|m|bn|k)?)", re.I)),
)


def _policy_hit(*values: str) -> Optional[str]:
    blob = " ".join(v.casefold() for v in values if v)
    for term in SENSITIVE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", blob):
            return term
    return None


def _clean_value(predicate: str, value: str) -> str:
    value = normalise_space(value).strip(" .,-:;\u2013\u2014")
    if predicate == "employees":
        value = value.replace(",", "")
    if predicate == "hq":
        value = value.strip()
    return value


STABLE_PREDICATES = frozenset({"founded", "employees", "hq", "ceo", "role", "funding"})


def _mentions_entity(quote: str, entity_name: str) -> bool:
    """Does the quote name the entity at all?

    Word boundaries matter: "valves" is not "valve", while "Valve Corporation"
    still matches a page that says only "Valve".
    """
    if not entity_name:
        return False
    haystack = normalise_space(quote).casefold()
    for token in re.findall(r"[a-z0-9]{3,}", entity_name.casefold()):
        if re.search(rf"\b{re.escape(token)}\b", haystack):
            return True
    return False


def _names_entity_first(quote: str, value: str, entity_name: str) -> bool:
    """Is the entity named before the value, not merely somewhere in the quote?

    A Wikipedia sentence, "A consumer group, based in France, filed a lawsuit
    against Valve", names Valve and states a location, but the location belongs
    to the group. Requiring the entity first makes that sentence unusable as
    evidence about Valve, at the cost of the occasional backwards construction
    ("in Bellevue, Valve..."), which is rejected and counted rather than
    guessed at.
    """
    if not entity_name:
        return False
    haystack = normalise_space(quote).casefold()
    needle = normalise_space(value).casefold()
    at = haystack.find(needle) if needle else -1
    if at <= 0:
        return False
    head = haystack[:at]
    for token in re.findall(r"[a-z0-9]{3,}", entity_name.casefold()):
        if re.search(rf"\b{re.escape(token)}\b", head):
            return True
    return False


def _accept(
    report: ExtractionReport,
    doc: Document,
    predicate: str,
    value: str,
    quote: str,
    text_norm: str,
    *,
    self_described: bool = True,
    entity_name: str = "") -> None:
    if predicate not in PREDICATES:
        report.reject(predicate, "predicate outside the closed set", quote)
        return
    value = _clean_value(predicate, value)
    if len(value) < 2:
        report.reject(predicate, "value too short", quote)
        return
    quote = normalise_space(quote)
    if len(quote) < MIN_QUOTE_CHARS:
        report.reject(predicate, "quote too short", quote)
        return
    if quote not in text_norm:
        report.reject(predicate, "quote is not verbatim in the source", quote)
        return
    if predicate in STABLE_PREDICATES and not self_described:
        # "Nvidia CEO Jensen Huang said..." is not a fact about the entity we
        # are building a dossier on, however true the sentence is.
        if not _mentions_entity(quote, entity_name):
            report.reject(predicate, "third-party page does not name the entity in the quote", quote)
            return
        if not _names_entity_first(quote, value, entity_name):
            report.reject(predicate, "third-party page attaches the value to another subject", quote)
            return
    hit = _policy_hit(value, quote)
    if hit:
        report.reject(predicate, f"sensitive category refused: {hit}", quote)
        return
    report.claims.append(
        ClaimDraft(
            predicate=predicate,
            value=value[:200],
            evidence=Evidence(
                source_url=doc.url,
                source_type=doc.source_type,
                quote=quote[:MAX_QUOTE_CHARS],
                retrieved_at=doc.retrieved_at,
                published_at=doc.published_at))
    )


def _title_core(title: str, domain: str) -> str:
    """Strip the site-name furniture out of a page title."""
    parts = [p.strip(" -, ·|:·") for p in re.split(r"[|·]|\s+[, -]\s+", title or "")]
    keep = [p for p in parts if p and (domain or "").casefold() not in p.casefold()]
    core = (keep or parts or [title])[0]
    return core[:120]


def _best_sentence(text: str, spans: list[tuple[int, int]], needle: str) -> str:
    """The sentence that best supports a title-derived value.

    A quote has to be *in* the page, but it should also be *about* the claim.
    Scoring by shared words is a cheap way to stop the nav bar becoming the
    evidence for what a company does.
    """
    words = {w.casefold() for w in _WORD.findall(needle or "")}
    best, best_score = "", 0
    for start, end in spans:
        sentence = text[start:end].strip()
        if len(sentence) < 40:
            continue
        score = len(words & {w.casefold() for w in _WORD.findall(sentence)})
        if score > best_score:
            best, best_score = sentence, score
    if best:
        return best
    return next((text[a:b].strip() for a, b in spans if len(text[a:b].split()) >= 6), "")


_ROLE = re.compile(
    r"\b(?:is|serves as|works as|joined as)\s+(?:the\s+|a\s+|an\s+)?"
    r"([A-Za-z][A-Za-z,'\-]{2,48}?)\s+(?:at|of|with)\s+([A-Z][A-Za-z0-9 .,'&\-]{1,60})")
_ROLE_ALT = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){1,2})\s*,\s*(?:the\s+)?"
    r"((?:CEO|CTO|CFO|COO|chief [a-z ]{3,24}|managing director|founder|co-founder|director|head of [A-Za-z ]{2,24}))"
    r"\s+(?:at|of)\s+([A-Z][A-Za-z0-9 .,'&\-]{1,60})")


def _person_role_pass(
    report: ExtractionReport,
    doc: Document,
    text_norm: str,
    spans: list[tuple[int, int]],
    *,
    self_described: bool = True,
    entity_name: str = "",
) -> None:
    """Professional role claims, which are the point of a person dossier.

    Only run for person entities: on an organisation page these patterns match
    sentences about other people, and a dossier on Acme must not claim its
    cleaner's job title.
    """
    for pattern in (_ROLE, _ROLE_ALT):
        for match in pattern.finditer(text_norm):
            groups = [g for g in match.groups() if g]
            value = " ".join(g.strip(",") for g in groups)
            if len(value) > 120:
                continue
            quote = _quote_for(text_norm, spans, match.start(), match.end())
            _accept(
                report, doc, "role", value, quote, text_norm,
                self_described=self_described, entity_name=entity_name)


def _first_sentence(text: str) -> str:
    normalised = normalise_space(text)
    match = re.match(r"(.{10,200}?[.!?])(\s|$)", normalised)
    return match.group(1) if match else normalised[:200]


def extract_document(
    doc: Document,
    report: Optional[ExtractionReport] = None,
    *,
    kind: str = "org",
    entity_name: str = "",
    entity_domain: str = "") -> ExtractionReport:
    report = report or ExtractionReport()
    if not doc.text.strip():
        report.reject("any", f"{doc.url}: empty document")
        return report

    text_norm = normalise_space(doc.text)
    spans = _sentences(text_norm)

    # A page speaking about itself needs no name in the sentence ("Founded in
    # 2014..." is fine on their own site). Anywhere else the quote has to name
    # the entity, or we are collecting facts about somebody else.
    self_described = doc.source_type in ("official", "registry") or (
        bool(entity_domain) and doc.domain == entity_domain
    )
    context = {"self_described": self_described, "entity_name": entity_name}

    for predicate, pattern in RULES:
        for match in pattern.finditer(text_norm):
            value = match.group(1)
            quote = _quote_for(text_norm, spans, match.start(1), match.end(1))
            _accept(report, doc, predicate, value, quote, text_norm, **context)

    # A news item is a dated headline: the claim is "this was reported".
    if doc.source_type == "news" and doc.title:
        first = text_norm[:400]
        quote = _quote_for(text_norm, spans, 0, min(1, len(text_norm)))
        if quote:
            _accept(report, doc, "news", doc.title, quote, text_norm, **context)

    # The page describing itself in one line is the best product claim. A site's
    # meta description is written for exactly this; a sentence picked out of the
    # body is the fallback, and only on the entity's own page. Third-party pages
    # are excluded on purpose: an article's meta description summarises the
    # article, so "Valve warns of slower Steam approvals" is not what Valve does.
    if self_described and doc.description and len(doc.description) >= 15 and not doc.description.startswith("("):
        value = _first_sentence(doc.description)
        _accept(report, doc, "product", value, value, text_norm, **context)
    elif doc.source_type == "official" and doc.title:
        core = _title_core(doc.title, doc.domain)
        sentence = _best_sentence(text_norm, spans, core)
        if sentence and len(sentence) >= 20 and sentence[:1].isupper():
            value = sentence[:200].rstrip(" .,;:")
            _accept(report, doc, "product", value, sentence, text_norm, **context)

    if kind == "person":
        _person_role_pass(report, doc, text_norm, spans, **context)

    _keep_one_product_per_quote(report, doc)
    return report


def _keep_one_product_per_quote(report: ExtractionReport, doc: Document) -> None:
    """Two product claims from one sentence is noise, not corroboration.

    Runs last, so the full sentence from the page title wins over the fragment a
    keyword rule pulled out of the same sentence.
    """
    keep: dict[str, ClaimDraft] = {}
    rest: list[ClaimDraft] = []
    for claim in report.claims:
        if claim.predicate != "product" or claim.evidence.source_url != doc.url:
            rest.append(claim)
            continue
        digest = claim.evidence.quote_hash
        current = keep.get(digest)
        if current is None or len(claim.value) > len(current.value):
            if current is not None:
                report.reject("product", "duplicate product quote in one document", current.evidence.quote)
            keep[digest] = claim
        else:
            report.reject("product", "duplicate product quote in one document", claim.evidence.quote)
    report.claims = rest + list(keep.values())


def extract(
    documents: Iterable[Document],
    *,
    kind: str = "org",
    entity_name: str = "",
    entity_domain: str = "",
) -> ExtractionReport:
    report = ExtractionReport()
    for doc in documents:
        extract_document(
            doc, report, kind=kind, entity_name=entity_name, entity_domain=entity_domain
        )
    return report


LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "predicate": {"type": "string", "enum": list(PREDICATES)},
                    "value": {"type": "string"},
                    "quote": {"type": "string", "description": "verbatim from the page"},
                },
                "required": ["predicate", "value", "quote"],
            },
        }
    },
    "required": ["claims"],
}

LLM_INSTRUCTIONS = (
    "Extract only facts stated in the page text. For each fact return the exact "
    "sentence from the page that states it as `quote`, copied character for "
    "character. Do not infer, summarise or combine sentences. If a fact is not "
    "stated plainly, omit it. Never return anything about health, religion, "
    "sexuality, politics, ethnicity or union membership."
)


def extract_with_llm(doc: Document, llm: Any, report: Optional[ExtractionReport] = None) -> ExtractionReport:
    """Add LLM-found claims, gated identically. Silent no-op if the model fails."""
    report = report or ExtractionReport()
    if llm is None:
        return report
    try:
        result = llm.complete_structured(
            instructions=LLM_INSTRUCTIONS,
            input=[{"type": "text", "text": doc.text[:12_000]}],
            json_schema=LLM_SCHEMA,
            schema_name="dossier_claims",
            purpose="dossier.extract")
        parsed = getattr(result, "parsed", None) or {}
    except Exception as exc:  # model unavailable, timeout, bad JSON
        report.reject("any", f"{doc.url}: model extraction failed ({type(exc).__name__})")
        return report

    text_norm = normalise_space(doc.text)
    for item in parsed.get("claims", []) if isinstance(parsed, dict) else []:
        if not isinstance(item, dict):
            continue
        _accept(
            report,
            doc,
            str(item.get("predicate", "")),
            str(item.get("value", "")),
            str(item.get("quote", "")),
            text_norm)
    return report
