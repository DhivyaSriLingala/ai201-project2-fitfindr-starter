# FitFindr

FitFindr is a multi-tool AI thrifting agent. A user describes a secondhand item,
size, and budget in natural language; the planner searches a local marketplace,
tests the best find against a wardrobe, and creates a shareable outfit caption.
It changes course when a search fails instead of blindly calling every tool.

## Run It

Everything lives in this repository. No generated project files are stored
outside the folder.

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` in the project root:

```text
GROQ_API_KEY=your_groq_key
```

Start the interface:

```powershell
python app.py
```

Open the local URL printed by Gradio, normally
`http://127.0.0.1:7860`. The app still works if Groq is unavailable because both
generative tools include local fallbacks.

## Project Map

| Location | What and why |
|---|---|
| `planning.md` | Implementation-ready tool contracts, conditional planning logic, state design, error table, architecture diagram, and interaction trace. |
| `tools.py` | All three required standalone tools, Groq calls, ranking logic, validation, and local fallback generators. |
| `agent.py` | Query parser, session state, and adaptive planning loop. |
| `app.py` | Responsive Gradio UI and mapping from session fields to result cards. |
| `tests/test_tools.py` | Isolated success and failure tests for every tool. |
| `tests/test_agent.py` | Retry, early-stop, parser, and exact state-passing tests. |
| `data/` | The supplied 40-listing marketplace and wardrobe schema. |
| `utils/data_loader.py` | Supplied data access helpers used by the tools. |

## Tool Inventory

### `search_listings(description, size=None, max_price=None) -> list[dict]`

- `description` (`str`): Item and style keywords.
- `size` (`str | None`): Optional alpha, waist, or shoe size.
- `max_price` (`float | None`): Optional inclusive price ceiling.
- Returns complete listing dictionaries sorted by weighted relevance and price.
- Uses `load_listings()` rather than re-reading or duplicating the dataset logic.

Search scores title, style tags, category, color, brand, and description with
different weights. It requires at least one direct semantic match, so a query
for size 8 combat boots cannot return unrelated size 8 sneakers merely because
both are shoes.

### `suggest_outfit(new_item, wardrobe) -> str`

- `new_item` (`dict`): The exact selected listing.
- `wardrobe` (`dict`): An object containing an `items` list.
- Returns one or two complete outfits with proportion, color, and styling notes.

With wardrobe items, the prompt names the user's real pieces and tells the model
not to invent others. With an empty wardrobe, it recommends general categories
and colors. Groq uses `llama-3.3-70b-versatile`; a local wardrobe-aware stylist
handles missing keys, network failures, or service errors.

### `create_fit_card(outfit, new_item) -> str`

- `outfit` (`str`): The exact output from `suggest_outfit`.
- `new_item` (`dict`): The same selected listing used by the stylist.
- Returns a casual two-to-four sentence outfit caption.

The prompt requires the item name, price, platform, and specific outfit mood.
Temperature is `1.05` for variation. A randomized local generator preserves the
same required details when Groq cannot respond.

## Planning Loop

`run_agent()` uses a `next_step` loop:

1. Parse the natural-language query into `description`, `size`, and `max_price`.
2. Search and store all results.
3. If strict search is empty and a size exists, remove only the size and retry
   once. Record the decision in `planner_trace`.
4. If the retry is empty, set an actionable error and return immediately.
5. Otherwise store the top result as `selected_item`.
6. Style that exact item with the session wardrobe.
7. Pass the exact outfit string and selected item into the fit-card tool.
8. Return the completed session.

This is conditional behavior: no-results sessions never call the styling or
caption tools, while size failures can take a retry branch before stopping.

## State Management

One session dictionary carries data through the full interaction:

```text
query -> parsed -> search_results -> selected_item
      -> outfit_suggestion -> fit_card
```

It also stores `wardrobe`, `retry_applied`, `planner_trace`, and `error`.
Tests assert that the same selected item object reaches both downstream tools
and that the exact outfit string reaches `create_fit_card`.

## Error Handling

| Failure | Response |
|---|---|
| Search returns no result | Retry once without size when possible. If still empty, explain what failed and suggest broader keywords or a higher budget. |
| Dataset is unreadable or input is invalid | Return `[]`; the planner uses its safe no-results path. |
| Wardrobe is empty | Produce a complete general outfit without claiming the user owns named pieces. |
| Groq is unavailable during styling | Use the local wardrobe-aware suggestion generator. |
| Outfit is blank | Return: `I need an outfit suggestion before I can create a fit card.` |
| Groq is unavailable during captioning | Use the varied local fit-card generator. |

Concrete test: `"designer ballgown size XXS under $5"` performs a strict search,
retries without size, then returns a useful no-results explanation. The session
leaves `selected_item`, `outfit_suggestion`, and `fit_card` empty.

## Verification

Run the complete suite:

```powershell
pytest tests -q
```

Current result: **15 passed**.

The suite covers relevant search, empty search, price and size filters, empty
wardrobe, malformed item input, empty outfit input, caption variation, query
parsing, state identity, fallback retry, and stopping before downstream calls.
A live Groq run was also checked with both a populated and empty wardrobe.

## UI Design

The interface in `app.py` uses a responsive editorial layout rather than the
default Gradio appearance:

- Oversized FitFindr wordmark and a concise explanation of the agent.
- One focused search panel with wardrobe context.
- A visible three-step process strip.
- Separate listing, styling, and caption cards with distinct color treatments.
- A visible "Smart fallback" note when the planner loosens size.
- Mobile breakpoints and useful empty/error states.

## Spec Reflection

The written spec made the state handoff and early-return rule unambiguous. It
prevented the common failure where all three tools run unconditionally and made
the planner tests straightforward.

Implementation diverged in one useful way: the starter only required stopping
after an empty search, while FitFindr now retries once without size first. I
added this after documenting it in `planning.md` because secondhand sizing is
inconsistent and a transparent, narrow fallback is less frustrating than an
immediate dead end. I also added local generation fallbacks so the UI remains
demonstrable during API outages.

## AI Usage

1. **Tool implementation:** I gave Codex the three Tool sections from
   `planning.md`, the supplied docstrings, and the `data_loader.py` contract.
   It produced the search, styling, and caption functions. I revised the search
   scoring to require a direct semantic match and added exact phrase weighting
   after testing showed that category synonyms could over-rank the wrong item.

2. **Planner and state:** I gave Codex the Planning Loop, State Management,
   Error Handling, and Mermaid Architecture sections. It produced the
   `next_step` loop and session fields. I kept the explicit retry/early-return
   structure, then added tests that assert object identity between
   `selected_item` and both downstream calls rather than checking values only.

3. **Interface:** I gave Codex the session contract and required three-panel
   workflow. It produced a custom Gradio layout. I revised the result rendering
   to use semantic HTML cards, added a visible retry note, strengthened mobile
   behavior, and avoided exposing raw session dictionaries to users.
