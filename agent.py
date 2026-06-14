"""FitFindr's adaptive planning loop and shared session state."""

from __future__ import annotations

import re

from tools import create_fit_card, search_listings, suggest_outfit


def _new_session(query: str, wardrobe: dict) -> dict:
    """Create the single state object shared by every step in one interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "retry_applied": False,
        "planner_trace": [],
    }


def _parse_query(query: str) -> dict:
    """Extract common price and size phrases while preserving useful search text."""
    cleaned = " ".join(query.strip().split())

    price_match = re.search(
        r"(?:under|below|less\s+than|max(?:imum)?(?:\s+price)?(?:\s+of)?|up\s+to)"
        r"\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", cleaned)
    max_price = float(price_match.group(1)) if price_match else None

    size_patterns = [
        r"\bsize\s+(US\s*)?(\d+(?:\.\d+)?|XXS|XS|S|M|L|XL|XXL)\b",
        r"\bin\s+(?:a\s+)?(?:size\s+)?(US\s*)?(\d+(?:\.\d+)?|XXS|XS|S|M|L|XL|XXL)\b",
    ]
    size = None
    size_span = None
    for pattern in size_patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            prefix = (match.group(1) or "").upper().strip()
            raw_size = match.group(2).upper()
            size = f"{prefix} {raw_size}".strip()
            size_span = match.span()
            break

    description = cleaned
    if price_match:
        description = description.replace(price_match.group(0), " ")
    if size_span:
        size_text = cleaned[size_span[0]:size_span[1]]
        description = description.replace(size_text, " ")

    description = re.sub(
        r"\b(i'?m|i am|looking for|find me|show me|can you find|please|what'?s out there"
        r"|how would i style it|how do i style it)\b",
        " ",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"[,.!?;:]", " ", description)
    description = re.sub(r"\b(?:under|below|less than|up to|in)\s*$", " ", description, flags=re.IGNORECASE)
    description = " ".join(description.split()).strip()

    return {
        "description": description or cleaned,
        "size": size,
        "max_price": max_price,
    }


def _tool_message_is_error(message: str) -> bool:
    if not isinstance(message, str) or not message.strip():
        return True
    normalized = message.strip().lower()
    return normalized.startswith("i need a valid") or normalized.startswith(
        "i need an outfit suggestion"
    )


def run_agent(query: str, wardrobe: dict) -> dict:
    """Run the next tool selected from current session state until completion."""
    session = _new_session(query, wardrobe)
    if not isinstance(query, str) or not query.strip():
        session["error"] = (
            "Tell me what kind of secondhand piece you want. You can include a "
            "size and budget, such as 'vintage graphic tee, size M, under $30.'"
        )
        return session

    next_step = "parse"
    while next_step != "done":
        if next_step == "parse":
            session["parsed"] = _parse_query(query)
            session["planner_trace"].append(
                {"step": "parse", "status": "complete", "details": session["parsed"].copy()}
            )
            next_step = "search"

        elif next_step == "search":
            parsed = session["parsed"]
            results = search_listings(
                parsed["description"],
                size=parsed["size"],
                max_price=parsed["max_price"],
            )
            session["search_results"] = results
            session["planner_trace"].append(
                {
                    "step": "search",
                    "status": "matched" if results else "empty",
                    "details": {
                        "size": parsed["size"],
                        "max_price": parsed["max_price"],
                        "result_count": len(results),
                    },
                }
            )

            if results:
                session["selected_item"] = results[0]
                next_step = "style"
            elif parsed["size"] and not session["retry_applied"]:
                original_size = parsed["size"]
                session["retry_applied"] = True
                parsed["size"] = None
                session["planner_trace"].append(
                    {
                        "step": "plan",
                        "status": "retry",
                        "details": f"No size {original_size} match; retrying without size.",
                    }
                )
                next_step = "search"
            else:
                budget = parsed["max_price"]
                budget_text = f" under ${budget:.0f}" if budget is not None else ""
                retry_text = (
                    " I also checked beyond your requested size."
                    if session["retry_applied"]
                    else ""
                )
                session["error"] = (
                    f"I couldn't find a relevant match for \"{parsed['description']}\""
                    f"{budget_text}.{retry_text} Try a broader item name, remove a "
                    "color or style detail, or raise the budget."
                )
                next_step = "done"

        elif next_step == "style":
            outfit = suggest_outfit(session["selected_item"], session["wardrobe"])
            session["planner_trace"].append(
                {
                    "step": "style",
                    "status": "complete" if not _tool_message_is_error(outfit) else "error",
                    "details": {"wardrobe_items": len(session["wardrobe"].get("items", []))},
                }
            )
            if _tool_message_is_error(outfit):
                session["error"] = outfit or "I found an item but could not style it."
                next_step = "done"
            else:
                session["outfit_suggestion"] = outfit
                next_step = "card"

        elif next_step == "card":
            card = create_fit_card(
                session["outfit_suggestion"],
                session["selected_item"],
            )
            session["planner_trace"].append(
                {
                    "step": "card",
                    "status": "complete" if not _tool_message_is_error(card) else "error",
                }
            )
            if _tool_message_is_error(card):
                session["error"] = card or "I styled the item but could not create a fit card."
            else:
                session["fit_card"] = card
            next_step = "done"

        else:
            session["error"] = f"The planner reached an unknown step: {next_step}."
            next_step = "done"

    return session


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    for test_query in (
        "vintage graphic tee under $30",
        "designer ballgown size XXS under $5",
    ):
        result = run_agent(test_query, get_example_wardrobe())
        print(f"\nQuery: {test_query}")
        print(f"Trace: {result['planner_trace']}")
        print(f"Error: {result['error']}")
        if result["selected_item"]:
            print(f"Found: {result['selected_item']['title']}")
