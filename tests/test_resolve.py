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
        _doc("https://harbour.example/team/sarah-chen", "Sarah Chen - Partner, Harbour Fund", "Sarah Chen is a partner at Harbour Fund, based in Sydney."),
        _doc("https://acme.example/team/sarah-chen", "Sarah Chen - Engineer, Acme Robotics", "Sarah Chen is a hardware engineer at Acme Robotics, based in Canberra."),
    ]


def test_two_same_name_people_are_ambiguous():
    result = resolve("Sarah Chen", documents=_sarah())
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_a_disambiguator_resolves_without_guessing():
    """The name is the person; the employer is why this Sarah Chen is the one.

    The old assertion checked "Acme" against the name, which passed only while
    the whole page title was being used as the name.
    """
    result = resolve("Sarah Chen", documents=_sarah(), disambiguator="Acme")
    assert result["status"] == "resolved"
    assert result["candidate"]["name"] == "Sarah Chen"
    assert "Acme" in result["candidate"]["disambiguator"]


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


def test_an_article_about_the_entity_is_not_a_competing_identity():
    docs = [
        _doc("https://acme.example/", "Acme Robotics", "Acme Robotics builds warehouse robots."),
        _doc(
            "https://news.example/acme",
            "Acme Robotics raises $40 million",
            "Acme Robotics raised $40 million in a Series B round.",
        ),
    ]
    result = resolve("Acme Robotics", documents=docs)
    assert result["status"] == "resolved"
    assert result["candidate"]["domain"] == "acme.example"


def test_ambiguous_message_lists_candidates():
    from dossier.resolve import ambiguous_message

    result = resolve("Sarah Chen", documents=_sarah())
    message = ambiguous_message(result)
    assert "Which one?" in message
    assert "Harbour Fund" in message and "Acme Robotics" in message


def test_a_page_title_does_not_become_the_entity_name():
    """The bug the live probe found: "About Us - Palo Alto Networks" as a name."""
    docs = [
        _doc(
            "https://www.paloaltonetworks.com/about-us",
            "About Us - Palo Alto Networks",
            "Palo Alto Networks protects the digital way of life.",
        )
    ]
    result = resolve("Palo Alto Networks", documents=docs)
    assert result["status"] == "resolved"
    assert result["candidate"]["name"] == "Palo Alto Networks"


def test_a_title_with_the_name_repeated_is_cleaned():
    docs = [
        _doc(
            "https://www.rocketlabusa.com/about-us/",
            "Rocket Lab | About Us | Rocket Lab",
            "Rocket Lab is an end-to-end space company.",
        )
    ]
    result = resolve("Rocket Lab", documents=docs)
    assert result["candidate"]["name"] == "Rocket Lab"


def test_a_title_with_only_navigation_falls_back_to_the_typed_name():
    docs = [_doc("https://acme.example/", "Home", "Acme Robotics builds warehouse robots.")]
    result = resolve("Acme Robotics", documents=docs)
    assert result["candidate"]["name"] == "Acme Robotics"


def test_a_profile_page_title_does_not_become_the_name():
    """The profile branch must strip the platform, not keep the whole title."""
    docs = [
        _doc(
            "https://www.linkedin.com/in/sarah-chen",
            "Sarah Chen - Engineer at Acme Robotics | LinkedIn",
            "Sarah Chen is a hardware engineer at Acme Robotics.",
        )
    ]
    result = resolve("Sarah Chen", documents=docs)
    assert result["status"] == "resolved"
    assert result["candidate"]["name"] == "Sarah Chen"
    assert "Acme Robotics" in result["candidate"]["disambiguator"]
    assert "LinkedIn" not in result["candidate"]["disambiguator"]
