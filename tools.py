"""Standalone tools used by the FitFindr planning agent."""

from __future__ import annotations

import os
import random
import re
from typing import Any

from dotenv import load_dotenv

from utils.data_loader import load_listings

load_dotenv()

MODEL_NAME = "llama-3.3-70b-versatile"

_STOP_WORDS = {
    "a", "an", "and", "are", "at", "be", "for", "from", "i", "im", "in",
    "is", "it", "like", "looking", "me", "mostly", "my", "of", "or", "out",
    "please", "show", "something", "that", "the", "to", "want", "wear", "with",
}

_SYNONYMS = {
    "tee": {"tee", "tshirt", "shirt", "top"},
    "tshirt": {"tee", "tshirt", "shirt", "top"},
    "shirt": {"tee", "tshirt", "shirt", "top"},
    "jacket": {"jacket", "outerwear", "windbreaker", "blazer"},
    "coat": {"coat", "jacket", "outerwear"},
    "pants": {"pants", "trousers", "bottoms", "jeans"},
    "trousers": {"pants", "trousers", "bottoms"},
    "jeans": {"jeans", "denim", "pants", "bottoms"},
    "skirt": {"skirt", "bottoms", "midi", "mini"},
    "dress": {"dress", "gown", "midi", "slip"},
    "boots": {"boots", "shoes", "combat"},
    "sneakers": {"sneakers", "shoes", "trainers"},
    "shoes": {"shoes", "boots", "sneakers", "heels"},
    "bag": {"bag", "purse", "accessories"},
}

_ITEM_TYPE_TERMS = {
    "boots": {"boot", "boots", "combat", "chelsea"},
    "sneakers": {"sneaker", "sneakers", "trainer", "trainers"},
    "skirt": {"skirt", "midi", "mini"},
    "dress": {"dress", "gown", "slip"},
    "jacket": {"jacket", "windbreaker", "blazer", "bomber"},
    "jeans": {"jean", "jeans", "denim"},
    "tee": {"tee", "tshirt"},
}

_REQUIRED_SUBTYPES = {"combat", "chelsea", "mary jane", "mary janes"}


def _get_groq_client() -> Any:
    """Return a configured Groq client or raise a clear configuration error."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to .env to enable AI-generated text."
        )
    # Import lazily so the local search tool remains independent of the LLM SDK.
    from groq import Groq

    return Groq(api_key=api_key)


def _tokens(value: Any) -> list[str]:
    """Normalize text-like data into meaningful lowercase tokens."""
    if isinstance(value, list):
        value = " ".join(str(part) for part in value)
    words = re.findall(r"[a-z0-9]+", str(value).lower().replace("t-shirt", "tshirt"))
    return [word for word in words if word not in _STOP_WORDS and len(word) > 1]


def _expanded_query_tokens(description: str) -> set[str]:
    tokens = set(_tokens(description))
    expanded = set(tokens)
    for token in tokens:
        expanded.update(_SYNONYMS.get(token, set()))
    return expanded


def _size_matches(requested: str, listing_size: str) -> bool:
    """Match common alpha, waist, and shoe sizes without substring accidents."""
    requested_norm = requested.strip().lower()
    listing_norm = listing_size.strip().lower()
    if not requested_norm:
        return True

    requested_numbers = re.findall(r"\d+(?:\.\d+)?", requested_norm)
    listing_numbers = re.findall(r"\d+(?:\.\d+)?", listing_norm)
    if requested_numbers:
        return any(number in listing_numbers for number in requested_numbers)

    requested_alpha = re.findall(r"(?<![a-z])(xxs|xs|s|m|l|xl|xxl)(?![a-z])", requested_norm)
    listing_alpha = re.findall(r"(?<![a-z])(xxs|xs|s|m|l|xl|xxl)(?![a-z])", listing_norm)
    if requested_alpha:
        return any(size in listing_alpha for size in requested_alpha)

    return requested_norm == listing_norm


def _matches_item_intent(description: str, listing_tokens: set[str]) -> bool:
    """Prevent a shared color or broad category from changing the requested item."""
    query_text = description.lower()
    query_tokens = set(_tokens(description))

    for subtype in _REQUIRED_SUBTYPES:
        if subtype in query_text:
            subtype_tokens = set(_tokens(subtype))
            if not subtype_tokens <= listing_tokens:
                return False

    for item_type, accepted_terms in _ITEM_TYPE_TERMS.items():
        if item_type in query_tokens and not listing_tokens & accepted_terms:
            return False

    return True


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """Return relevant local listings that satisfy optional size and price filters."""
    if not isinstance(description, str) or not description.strip():
        return []
    if max_price is not None:
        try:
            max_price = float(max_price)
        except (TypeError, ValueError):
            return []
        if max_price < 0:
            return []

    try:
        listings = load_listings()
    except (OSError, ValueError, TypeError):
        return []

    direct_query_tokens = set(_tokens(description))
    query_tokens = _expanded_query_tokens(description)
    ranked: list[tuple[float, float, dict]] = []

    for listing in listings:
        try:
            price = float(listing["price"])
            listing_size = str(listing["size"])
        except (KeyError, TypeError, ValueError):
            continue

        if max_price is not None and price > max_price:
            continue
        if size and not _size_matches(size, listing_size):
            continue

        title_tokens = set(_tokens(listing.get("title", "")))
        tag_tokens = set(_tokens(listing.get("style_tags", [])))
        category_tokens = set(_tokens(listing.get("category", "")))
        color_tokens = set(_tokens(listing.get("colors", [])))
        description_tokens = set(_tokens(listing.get("description", "")))
        brand_tokens = set(_tokens(listing.get("brand") or ""))

        direct_listing_tokens = (
            title_tokens
            | tag_tokens
            | color_tokens
            | description_tokens
            | brand_tokens
        )
        if not _matches_item_intent(description, direct_listing_tokens):
            continue
        # A category synonym alone ("boots" -> "shoes") is too weak to prove relevance.
        if not direct_query_tokens & direct_listing_tokens:
            continue

        score = (
            5 * len(query_tokens & title_tokens)
            + 4 * len(query_tokens & tag_tokens)
            + 3 * len(query_tokens & category_tokens)
            + 2 * len(query_tokens & color_tokens)
            + 2 * len(query_tokens & brand_tokens)
            + len(query_tokens & description_tokens)
        )
        phrase = description.strip().lower()
        title_text = str(listing.get("title", "")).lower()
        tag_text = " ".join(listing.get("style_tags", [])).lower()
        searchable = " ".join(
            [
                str(listing.get("title", "")),
                " ".join(listing.get("style_tags", [])),
                str(listing.get("description", "")),
            ]
        ).lower()
        if phrase in searchable:
            score += 8
        query_phrases = [
            " ".join(_tokens(description)[index:index + 2])
            for index in range(max(0, len(_tokens(description)) - 1))
        ]
        score += 6 * sum(phrase in title_text for phrase in query_phrases)
        score += 3 * sum(phrase in tag_text for phrase in query_phrases)

        if score > 0:
            ranked.append((float(score), price, listing))

    ranked.sort(key=lambda result: (-result[0], result[1], result[2].get("title", "")))
    return [listing for _, _, listing in ranked]


def _wardrobe_summary(items: list[dict]) -> str:
    lines = []
    for item in items:
        colors = ", ".join(item.get("colors", [])) or "unspecified color"
        tags = ", ".join(item.get("style_tags", [])) or "no style tags"
        notes = item.get("notes") or "no fit notes"
        lines.append(
            f"- {item.get('name', 'Unnamed item')} ({item.get('category', 'item')}); "
            f"colors: {colors}; style: {tags}; notes: {notes}"
        )
    return "\n".join(lines)


def _choose_wardrobe_piece(items: list[dict], category: str) -> dict | None:
    matches = [item for item in items if item.get("category") == category]
    return matches[0] if matches else None


def _local_outfit_suggestion(new_item: dict, wardrobe: dict) -> str:
    """Create a useful deterministic styling result when the LLM is unavailable."""
    title = new_item.get("title", "this thrifted piece")
    category = new_item.get("category", "item")
    colors = new_item.get("colors") or ["neutral"]
    item_color = colors[0]
    items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if not items:
        pairings = {
            "tops": "relaxed dark-wash jeans, clean chunky sneakers, and a cropped jacket",
            "bottoms": "a fitted white tank, a lightweight denim layer, and simple sneakers",
            "outerwear": "a plain fitted tee, wide-leg trousers, and low-profile sneakers",
            "shoes": "straight-leg jeans, a simple ribbed top, and a compact crossbody bag",
            "accessories": "a monochrome tee-and-trouser base with understated shoes",
        }
        base = pairings.get(category, "a neutral fitted top, relaxed trousers, and simple shoes")
        return (
            f"Build the look around {title} with {base}. Keep the palette mostly "
            f"neutral so the {item_color} detail feels intentional, then repeat one "
            "color from the item in a small accessory. Balance the silhouette with "
            "one fitted piece and one relaxed piece."
        )

    needed_categories = {
        "tops": ["bottoms", "shoes", "outerwear", "accessories"],
        "bottoms": ["tops", "shoes", "outerwear", "accessories"],
        "outerwear": ["tops", "bottoms", "shoes", "accessories"],
        "shoes": ["tops", "bottoms", "outerwear", "accessories"],
        "accessories": ["tops", "bottoms", "shoes", "outerwear"],
    }.get(category, ["tops", "bottoms", "shoes", "accessories"])

    selected = [
        piece for target in needed_categories
        if (piece := _choose_wardrobe_piece(items, target)) is not None
    ]
    names = [piece.get("name", "a wardrobe staple") for piece in selected[:3]]
    while len(names) < 3:
        names.append(["a neutral base layer", "relaxed trousers", "simple sneakers"][len(names)])

    return (
        f"Make {title} the focal point with your {names[0]}, {names[1]}, and "
        f"{names[2]}. The mix keeps the silhouette balanced while echoing the "
        f"{item_color} tone without looking overly matched. Finish with a small "
        "front tuck or one rolled cuff for shape, and keep the accessories minimal."
    )


def _call_groq(system_prompt: str, user_prompt: str, temperature: float) -> str:
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=360,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("Groq returned an empty response.")
    return content.strip()


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """Suggest complete outfits using the selected listing and available wardrobe."""
    if not isinstance(new_item, dict) or not new_item.get("title"):
        return "I need a valid selected item before I can suggest an outfit."

    if not isinstance(wardrobe, dict):
        wardrobe = {"items": []}
    items = wardrobe.get("items", [])
    if not isinstance(items, list):
        items = []
    safe_wardrobe = {"items": items}

    item_details = (
        f"Title: {new_item.get('title')}\n"
        f"Category: {new_item.get('category', 'unknown')}\n"
        f"Colors: {', '.join(new_item.get('colors', [])) or 'unknown'}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', [])) or 'none'}\n"
        f"Description: {new_item.get('description', '')}"
    )
    if items:
        wardrobe_context = _wardrobe_summary(items)
        request = (
            f"NEW THRIFT FIND\n{item_details}\n\nUSER WARDROBE\n{wardrobe_context}\n\n"
            "Suggest two complete, distinct outfits. Name only wardrobe pieces that "
            "appear above, explain silhouette/color logic briefly, and include one "
            "specific styling adjustment such as a cuff, tuck, or layer."
        )
    else:
        request = (
            f"NEW THRIFT FIND\n{item_details}\n\nThe user has an empty wardrobe.\n"
            "Suggest one complete outfit using general item categories, colors, and "
            "proportions. Be encouraging and useful without pretending the user owns "
            "specific pieces."
        )

    try:
        return _call_groq(
            "You are FitFindr, a concise secondhand fashion stylist. Give practical, "
            "specific advice in friendly plain language. Do not use markdown headings.",
            request,
            temperature=0.75,
        )
    except Exception:
        return _local_outfit_suggestion(new_item, safe_wardrobe)


def _local_fit_card(outfit: str, new_item: dict) -> str:
    title = new_item.get("title", "thrifted find")
    price = float(new_item.get("price", 0))
    platform = str(new_item.get("platform", "the thrift feed")).title()
    vibe_tags = new_item.get("style_tags") or ["secondhand", "personal style"]
    vibe = random.choice(vibe_tags)
    openings = [
        "Found the piece that pulled the whole look together.",
        "A secondhand find with main-character energy.",
        "Proof that the best outfits start with one really good find.",
        "This one earned an immediate place in the rotation.",
    ]
    endings = [
        "Worn-in, easy, and exactly the right amount of undone.",
        "The final mood is relaxed, intentional, and ready to repeat.",
        "A little texture, a little contrast, and a lot of personality.",
        "Consider this the outfit formula for the week.",
    ]
    detail = re.split(r"(?<=[.!?])\s+", outfit.strip())[0]
    return (
        f"{random.choice(openings)} {title} was ${price:.0f} on {platform}, and "
        f"the {vibe} mood is doing all the work. {detail} {random.choice(endings)}"
    )


def create_fit_card(outfit: str, new_item: dict) -> str:
    """Generate a short shareable caption for a completed outfit."""
    if not isinstance(outfit, str) or not outfit.strip():
        return "I need an outfit suggestion before I can create a fit card."
    if not isinstance(new_item, dict) or not new_item.get("title"):
        return "I need a valid selected item before I can create a fit card."

    request = (
        f"ITEM: {new_item.get('title')}\n"
        f"PRICE: ${float(new_item.get('price', 0)):.2f}\n"
        f"PLATFORM: {new_item.get('platform', 'secondhand marketplace')}\n"
        f"OUTFIT: {outfit.strip()}\n\n"
        "Write a two-to-four sentence social caption. Mention the item name, price, "
        "and platform naturally exactly once. Capture the specific outfit vibe and "
        "sound like a real person sharing an outfit, not a product listing. Do not "
        "use hashtags, quotation marks, a heading, or instructions."
    )
    try:
        return _call_groq(
            "You write fresh, casual OOTD captions for FitFindr. Keep them concise, "
            "specific, warm, and different for different items and outfits.",
            request,
            temperature=1.05,
        )
    except Exception:
        return _local_fit_card(outfit, new_item)
