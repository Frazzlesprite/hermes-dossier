"""Planning: the questions a brief is built to answer.

Eight to sixteen concrete questions, derived from the entity kind and from the
gaps a previous snapshot revealed. These steer which adapters run and which
queries are sent; they are not printed to the reader.
"""

from __future__ import annotations

from typing import Iterable, Optional

ORG_QUESTIONS = (
    "What does {name} sell, in one sentence a stranger would understand?",
    "When was {name} founded, and where is it headquartered?",
    "How many people does {name} employ, and where do they work?",
    "Who runs {name} today, and how long have they held the role?",
    "Has {name} raised money, from whom, and how much?",
    "What are {name}'s main products or services?",
    "What has changed at {name} in the last 90 days?",
    "Who are {name}'s customers, and who are its competitors?",
    "What could go wrong with {name} that a supplier should know about?",
)

PERSON_QUESTIONS = (
    "What is {name}'s current professional role, and at which organisation?",
    "What has {name} done before this role?",
    "What is {name} publicly known for?",
    "Has anything about {name}'s professional role changed in the last 90 days?",
    "Is there any public disagreement about {name}'s role or record?",
)


def research_questions(
    name: str,
    *,
    kind: str = "org",
    gaps: Optional[Iterable[str]] = None,
) -> list[str]:
    base = PERSON_QUESTIONS if kind == "person" else ORG_QUESTIONS
    questions = [q.format(name=name) for q in base]
    for gap in gaps or ():
        questions.append(f"What can be established about {name}'s {gap}, and from which source?")
    return questions[:16]


def search_queries(name: str, *, kind: str = "org", domain: str | None = None) -> list[str]:
    """The queries handed to the search adapter. Few, concrete, and bounded."""
    queries = [f'"{name}"']
    if domain:
        queries.append(f'site:{domain} "{name}"')
    queries.append(f'"{name}" headcount OR employees OR revenue')
    queries.append(f'"{name}" funding OR raised OR acquisition')
    return queries
