"""Tests for FitFindr's planning decisions and state handoffs."""

import agent
from utils.data_loader import get_example_wardrobe


def test_parse_query_extracts_filters():
    parsed = agent._parse_query("vintage graphic tee under $30, size M")

    assert parsed == {
        "description": "vintage graphic tee",
        "size": "M",
        "max_price": 30.0,
    }


def test_agent_passes_exact_state_between_tools(monkeypatch):
    selected = {
        "id": "test",
        "title": "Test Tee",
        "description": "Test",
        "category": "tops",
        "style_tags": ["graphic tee"],
        "size": "M",
        "condition": "good",
        "price": 20.0,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    }
    wardrobe = get_example_wardrobe()
    captured = {}

    monkeypatch.setattr(agent, "search_listings", lambda *args, **kwargs: [selected])

    def fake_style(item, received_wardrobe):
        captured["style_item"] = item
        captured["wardrobe"] = received_wardrobe
        return "Exact outfit text"

    def fake_card(outfit, item):
        captured["card_outfit"] = outfit
        captured["card_item"] = item
        return "Exact fit card"

    monkeypatch.setattr(agent, "suggest_outfit", fake_style)
    monkeypatch.setattr(agent, "create_fit_card", fake_card)

    session = agent.run_agent("graphic tee size M under $30", wardrobe)

    assert captured["style_item"] is session["selected_item"]
    assert captured["card_item"] is session["selected_item"]
    assert captured["wardrobe"] is session["wardrobe"]
    assert captured["card_outfit"] is session["outfit_suggestion"]
    assert session["fit_card"] == "Exact fit card"


def test_agent_retries_without_size(monkeypatch):
    calls = []

    def fake_search(description, size=None, max_price=None):
        calls.append(size)
        if size:
            return []
        return [
            {
                "id": "retry",
                "title": "Band Tee",
                "description": "Faded tee",
                "category": "tops",
                "style_tags": ["band tee"],
                "size": "L",
                "condition": "good",
                "price": 22.0,
                "colors": ["black"],
                "brand": None,
                "platform": "depop",
            }
        ]

    monkeypatch.setattr(agent, "search_listings", fake_search)
    monkeypatch.setattr(agent, "suggest_outfit", lambda item, wardrobe: "Outfit")
    monkeypatch.setattr(agent, "create_fit_card", lambda outfit, item: "Card")

    session = agent.run_agent(
        "band tee size M under $30",
        get_example_wardrobe(),
    )

    assert calls == ["M", None]
    assert session["retry_applied"] is True
    assert session["fit_card"] == "Card"
    assert any(event["status"] == "retry" for event in session["planner_trace"])


def test_agent_stops_after_empty_search(monkeypatch):
    called = {"style": False, "card": False}
    monkeypatch.setattr(agent, "search_listings", lambda *args, **kwargs: [])

    def should_not_style(*args):
        called["style"] = True
        return "Unexpected"

    def should_not_card(*args):
        called["card"] = True
        return "Unexpected"

    monkeypatch.setattr(agent, "suggest_outfit", should_not_style)
    monkeypatch.setattr(agent, "create_fit_card", should_not_card)

    session = agent.run_agent(
        "designer ballgown size XXS under $5",
        get_example_wardrobe(),
    )

    assert session["error"]
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    assert called == {"style": False, "card": False}
