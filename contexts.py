"""What the dossier is *for*, and how that changes it.

A brief written for a job interview and a brief written for a sales call want
different questions and different risks. The same evidence serves both, so the
context only changes the framing: questions, section labels, and what the
reader is told to do next.

Inference is keyword based and deliberately conservative. If nothing matches,
the brief falls back to gap questions, which are still useful.
"""

from __future__ import annotations

from typing import Iterable

CONTEXTS: dict[str, dict[str, object]] = {
    "general": {
        "label": "General research",
        "risks_title": "Risks",
        "questions": [],
    },
    "interview": {
        "label": "Job interview",
        "risks_title": "What to be ready for",
        "questions": [
            "Who would I report to, and what has the team shipped in the last six months?",
            "What is {name} expecting this role to change in the first ninety days?",
            "How does {name} measure success in this team, and who reviews it?",
        ],
    },
    "sales": {
        "label": "Sales meeting",
        "risks_title": "Objections to expect",
        "questions": [
            "What is {name} spending today, with whom, and when does it renew?",
            "Who signs off on a purchase like this, and what does procurement require?",
            "What has changed at {name} that makes this urgent this quarter?",
        ],
    },
    "partnership": {
        "label": "Partnership discussion",
        "risks_title": "Fit and friction",
        "questions": [
            "What does {name} need that it cannot build or buy quickly itself?",
            "Who owns partnerships at {name}, and what does the approval path look like?",
            "What would a first pilot look like, and who would sponsor it internally?",
        ],
    },
    "diligence": {
        "label": "Due diligence",
        "risks_title": "What would hurt",
        "questions": [
            "Where do the sources disagree, and which of those numbers is load-bearing?",
            "How concentrated is {name} in its largest customers and key staff?",
            "What has {name} stopped saying publicly in the last year?",
        ],
    },
    "supplier": {
        "label": "Supplier review",
        "risks_title": "Delivery risk",
        "questions": [
            "What would {name} fail to deliver if it lost its largest customer?",
            "Who actually runs delivery at {name}, and how long have they been there?",
            "What has changed at {name} since we last reviewed them?",
        ],
    },
}

ALIASES = {
    "interview": ("interview", "hiring", "job", "role", "recruiter", "candidate"),
    "sales": ("sales", "sell", "pitch", "prospect", "demo", "quota", "deal"),
    "partnership": ("partner", "partnership", "collaborat", "alliance", "integrat"),
    "diligence": ("diligence", "acquire", "acquisition", "invest", "merger", "m&a", "vendor risk"),
    "supplier": ("supplier", "vendor", "procure", "contract renewal", "sourcing"),
}


def normalise(value: str | None) -> str:
    value = (value or "").strip().lower().replace("_", " ")
    return value if value in CONTEXTS else ""


def infer(purpose: str | None, kind: str = "org") -> str:
    """Best guess of the context from the one line the user typed."""
    text = (purpose or "").casefold()
    for context, words in ALIASES.items():
        if any(word in text for word in words):
            return context
    if kind == "person":
        return "interview"
    return "general"


def label(context: str) -> str:
    return str(CONTEXTS.get(context, CONTEXTS["general"])["label"])


def risks_title(context: str) -> str:
    return str(CONTEXTS.get(context, CONTEXTS["general"])["risks_title"])


def questions(context: str, name: str) -> list[str]:
    templates = CONTEXTS.get(context, CONTEXTS["general"]).get("questions") or []
    return [str(template).format(name=name) for template in templates]


def merge(context: str, name: str, gap_questions: Iterable[str], limit: int = 3) -> list[str]:
    """Context questions first, then the gap questions, capped at `limit`.

    A context question is more useful to someone with a meeting on Tuesday, so
    it outranks a generic gap prompt. Nothing is invented: every template is
    about what to ask, not what is true.
    """
    picked: list[str] = []
    for question in list(questions(context, name)) + list(gap_questions):
        if question not in picked:
            picked.append(question)
        if len(picked) >= limit:
            break
    return picked
