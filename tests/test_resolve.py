"""Entity resolution: a name must not silently land on the wrong entity."""

from __future__ import annotations

from dossier.models import Document
from dossier.resolve import resolve

from fakeweb import AMBIGUOUS_A, AMBIGUOUS_B


def _doc(url: str, title: str, text: str) -> Document:
    return Document(
        url=url,
        title=title,
        text=text,
        source_type="search",
        retrieved_at="2026-11-08T00:00:00Z",
        domain=url.split("/")[2],
    )


def _sarah() -> list[Document]:
    return [
        _doc("https://harbour.example/team/sarah-chen", "Sarah Chen — Partner, Harbour Fund", "Sarah Chen is a partner at Harbour Fund, based in Sydney."),
        _doc("https://acme.example/team/sarah-chen", "Sarah Chen — Engineer, Acme Robotics", "Sarah Chen is a hardware engineer at Acme Robotics, based in Canberra."),
    ]


def test_two_same_name_people_are_ambiguous():
    result = resolve("Sarah Chen", documents=_sarah())
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_a_disambiguator_resolves_without_guessing():
    result = resolve("Sarah Chen", documents=_sarah(), disambiguator="Acme")
    assert result["status"] == "resolved"
    assert "Acme" in result["candidate"]["name"]


def test_a_domain_pins_the_entity():
    result = resolve("Acme", domain="https://www.acme.example/about")
    assert result["status"] == "resolved"
    assert result["candidate"]["domain"] == "acme.example"


def test_nothing_is_not_a_result():
    result = resolve("Nobody At All", documents=[])
    assert result["status"] == "not_found"


def test_an_unrelated_page_does_not_create_a_candidate():
    unrelated = [_doc("https://other.example/post", "Our favourite shops", "A list of shops we like, nothing about Acme.")]
    assert resolve("Acme Robotics", documents=unrelated)["status"] == "not_found"


def test_ambiguous_message_lists_candidates():
    from dossier.resolve import ambiguous_message

    result = resolve("Sarah Chen", documents=_sarah())
    message = ambiguous_message(result)
    assert "Which one?" in message
    assert "Harbour Fund" in message and "Acme Robotics" in message
