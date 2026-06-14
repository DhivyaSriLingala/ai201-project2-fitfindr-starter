"""Unit tests for each FitFindr tool in isolation."""

import tools
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


def test_search_returns_relevant_results():
    results = tools.search_listings("vintage graphic tee", size=None, max_price=50)

    assert isinstance(results, list)
    assert results
    assert "graphic tee" in (
        results[0]["title"] + " " + " ".join(results[0]["style_tags"])
    ).lower()


def test_search_empty_results():
    results = tools.search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = tools.search_listings("jacket", size=None, max_price=50)
    assert results
    assert all(item["price"] <= 50 for item in results)


def test_search_size_filter_does_not_return_wrong_item_type():
    results = tools.search_listings("black combat boots", size="8", max_price=None)
    assert results == []


def test_search_relaxed_size_still_respects_requested_subtype():
    results = tools.search_listings("black combat boots", size=None, max_price=None)
    assert results == []


def test_general_boot_search_can_return_boots():
    results = tools.search_listings("boots", size=None, max_price=None)
    assert results
    assert "boot" in results[0]["title"].lower()


def test_suggest_outfit_uses_wardrobe_when_llm_fails(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_call_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    item = tools.search_listings("graphic tee", max_price=30)[0]

    suggestion = tools.suggest_outfit(item, get_example_wardrobe())

    assert suggestion
    assert "Baggy straight-leg jeans" in suggestion


def test_suggest_outfit_handles_empty_wardrobe(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_call_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    item = tools.search_listings("graphic tee", max_price=30)[0]

    suggestion = tools.suggest_outfit(item, get_empty_wardrobe())

    assert suggestion
    assert "Build the look" in suggestion


def test_suggest_outfit_rejects_missing_item():
    message = tools.suggest_outfit({}, get_example_wardrobe())
    assert "valid selected item" in message


def test_create_fit_card_handles_empty_outfit():
    item = tools.search_listings("graphic tee", max_price=30)[0]
    message = tools.create_fit_card("", item)
    assert message == "I need an outfit suggestion before I can create a fit card."


def test_create_fit_card_falls_back_and_varies(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_call_groq",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    item = tools.search_listings("graphic tee", max_price=30)[0]
    outfit = "Wear it with dark jeans, white sneakers, and a cropped jacket."

    cards = {tools.create_fit_card(outfit, item) for _ in range(10)}

    assert len(cards) > 1
    assert all(item["title"] in card for card in cards)
    assert all(f"${item['price']:.0f}" in card for card in cards)
