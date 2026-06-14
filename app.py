"""Polished Gradio interface for the FitFindr agent."""

from __future__ import annotations

import html
import warnings

import gradio as gr
from starlette.exceptions import StarletteDeprecationWarning

from agent import run_agent
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe

warnings.filterwarnings(
    "ignore",
    message=(
        "'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. "
        "Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead."
    ),
    category=StarletteDeprecationWarning,
)


def _escape(value: object) -> str:
    return html.escape(str(value))


def _listing_card(session: dict) -> str:
    item = session["selected_item"]
    brand = item.get("brand") or "Independent seller"
    tags = " ".join(
        f'<span class="tag">{_escape(tag)}</span>' for tag in item.get("style_tags", [])[:4]
    )
    retry_note = ""
    if session["retry_applied"]:
        retry_note = (
            '<div class="notice"><strong>Smart fallback:</strong> No exact size match '
            "appeared, so FitFindr widened only the size filter.</div>"
        )
    return f"""
    <article class="result-card listing-card">
      <div class="eyebrow">01 / THE FIND</div>
      <div class="platform">{_escape(item["platform"])}</div>
      <h2>{_escape(item["title"])}</h2>
      <p class="brand">{_escape(brand)}</p>
      <div class="price-row">
        <span class="price">${float(item["price"]):.0f}</span>
        <span class="meta">{_escape(item["size"])} &middot; {_escape(item["condition"])}</span>
      </div>
      <p class="description">{_escape(item["description"])}</p>
      <div class="tags">{tags}</div>
      {retry_note}
    </article>
    """


def _text_card(number: str, eyebrow: str, title: str, text: str, card_class: str) -> str:
    paragraphs = "".join(
        f"<p>{_escape(part)}</p>" for part in text.splitlines() if part.strip()
    )
    return f"""
    <article class="result-card {card_class}">
      <div class="eyebrow">{number} / {eyebrow}</div>
      <h2>{title}</h2>
      <div class="card-copy">{paragraphs}</div>
    </article>
    """


def _error_card(message: str) -> str:
    return f"""
    <article class="result-card error-card">
      <div class="eyebrow">SEARCH PAUSED</div>
      <h2>No strong match yet.</h2>
      <p>{_escape(message)}</p>
      <div class="error-tip">Try: "black boots under $60" or "90s jacket size M".</div>
    </article>
    """


def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """Run one agent session and map its state to the three visual result cards."""
    if not isinstance(user_query, str) or not user_query.strip():
        message = (
            "Describe the piece you want to find. A useful request includes an item, "
            "and optionally a size or budget."
        )
        return _error_card(message), "", ""

    wardrobe = (
        get_empty_wardrobe()
        if wardrobe_choice == "Start with an empty wardrobe"
        else get_example_wardrobe()
    )
    session = run_agent(user_query.strip(), wardrobe)

    if session["error"]:
        return _error_card(session["error"]), "", ""

    listing = _listing_card(session)
    outfit = _text_card(
        "02",
        "THE STYLING",
        "Wear it your way.",
        session["outfit_suggestion"],
        "outfit-card",
    )
    fit_card = _text_card(
        "03",
        "THE CAPTION",
        "Ready to share.",
        session["fit_card"],
        "caption-card",
    )
    return listing, outfit, fit_card


EXAMPLE_QUERIES = [
    ["vintage graphic tee under $30, size M", "Use my sample wardrobe"],
    ["90s track jacket in size M", "Use my sample wardrobe"],
    ["flowy midi skirt under $40", "Use my sample wardrobe"],
    ["black combat boots size 8", "Start with an empty wardrobe"],
    ["designer ballgown size XXS under $5", "Use my sample wardrobe"],
]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');

:root {
  color-scheme: light;
  --ink: #201f1b;
  --cream: #f4efe5;
  --paper: #fffdf8;
  --acid: #d9ff58;
  --coral: #ff765d;
  --violet: #7867ff;
  --line: rgba(32,31,27,.18);
  --body-background-fill: var(--cream);
  --body-text-color: var(--ink);
  --body-text-color-subdued: #625f57;
  --background-fill-primary: var(--paper);
  --background-fill-secondary: #eee8dc;
  --border-color-primary: var(--ink);
}

.gradio-container {
  max-width: none !important;
  min-height: 100vh;
  background:
    radial-gradient(circle at 88% 8%, rgba(120,103,255,.16), transparent 24rem),
    linear-gradient(135deg, rgba(217,255,88,.16), transparent 34rem),
    var(--cream);
  color: var(--ink);
  font-family: "Manrope", sans-serif;
}

.gradio-container,
.gradio-container .prose,
.gradio-container p,
.gradio-container h1,
.gradio-container h2,
.gradio-container h3,
.gradio-container label {
  color: var(--ink);
}

.main-shell { max-width: 1240px; margin: 0 auto; padding: 34px 24px 64px; }
.hero { display:grid; grid-template-columns: 1.25fr .75fr; gap: 32px; align-items:end; padding: 34px 0 42px; }
.kicker, .eyebrow { color:var(--ink); font: 500 12px/1.3 "DM Mono", monospace; letter-spacing:.14em; text-transform:uppercase; }
.hero h1 { color:var(--ink) !important; font-size: clamp(64px, 10vw, 140px); line-height:.76; letter-spacing:-.085em; margin:16px 0 24px; font-weight:800; }
.hero h1 span { color: var(--violet); }
.hero-copy { color:#49463f !important; font-size:19px; line-height:1.55; max-width:620px; margin:0; }
.hero-note { color:var(--ink); border-left: 2px solid var(--ink); padding:8px 0 8px 20px; font: 500 14px/1.6 "DM Mono", monospace; }

.search-panel { background:var(--paper); border:1px solid var(--ink); box-shadow:8px 8px 0 var(--ink); padding:24px; margin-bottom:34px; }
.search-panel > div { color:#fff; }
.search-panel label, .search-panel label span { color:#fff !important; font:600 13px/1.3 "DM Mono", monospace !important; letter-spacing:.04em; text-transform:uppercase; }
.search-panel textarea { color:#fff !important; caret-color:var(--acid); border:0 !important; border-bottom:2px solid #48484b !important; border-radius:0 !important; background:transparent !important; font-size:19px !important; padding:15px 2px !important; box-shadow:none !important; }
.search-panel textarea::placeholder { color:#aaa9ad !important; }
.search-panel .wrap { gap:22px; }
.find-button, .find-button button { min-height:56px; background:var(--ink) !important; color:white !important; border:1px solid var(--ink) !important; border-radius:0 !important; font-weight:800 !important; letter-spacing:.02em; }
.find-button:hover, .find-button button:hover { background:var(--violet) !important; transform:translate(-2px,-2px); box-shadow:4px 4px 0 var(--ink); }

.process-strip { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid var(--ink); margin:24px 0 34px; background:rgba(255,253,248,.5); }
.process-step { color:#6c675e; padding:16px 18px; border-right:1px solid var(--ink); font:500 13px/1.4 "DM Mono", monospace; }
.process-step:last-child { border-right:0; }
.process-step strong { color:var(--ink); display:block; font-family:"Manrope",sans-serif; font-size:16px; margin-top:4px; }

.results-grid { gap:18px !important; align-items:stretch; }
.result-html, .result-html > div { height:100%; }
.result-card { color:var(--ink); min-height:520px; height:520px; padding:25px; border:1px solid var(--ink); background:var(--paper); box-sizing:border-box; position:relative; overflow:hidden; }
.result-card * { color:inherit; }
.result-card:after { content:""; position:absolute; width:90px; height:90px; right:-35px; bottom:-35px; border:1px solid var(--ink); transform:rotate(18deg); opacity:.25; }
.listing-card { box-shadow:inset 0 8px 0 var(--acid); }
.outfit-card { box-shadow:inset 0 8px 0 var(--coral); }
.caption-card { background:var(--ink); color:var(--paper) !important; box-shadow:inset 0 8px 0 var(--violet); }
.caption-card h2, .caption-card p, .caption-card .card-copy { color:var(--paper) !important; }
.error-card { min-height:250px; box-shadow:inset 0 8px 0 var(--coral); }
.result-card h2 { color:var(--ink); font-size:29px; line-height:1.08; letter-spacing:-.04em; margin:20px 0 7px; }
.platform { position:absolute; right:22px; top:22px; padding:5px 9px; border:1px solid currentColor; font:500 11px "DM Mono",monospace; text-transform:uppercase; }
.brand, .meta { color:#6e6a61 !important; font-size:13px; text-transform:capitalize; }
.caption-card .eyebrow { color:var(--acid); }
.price-row { display:flex; justify-content:space-between; align-items:end; margin:25px 0 16px; padding-bottom:12px; border-bottom:1px solid var(--line); }
.price { font-size:38px; font-weight:800; line-height:1; }
.description, .card-copy { color:#3f3c36; font-size:15px; line-height:1.65; }
.card-copy { max-height:365px; overflow-y:auto; padding-right:8px; scrollbar-color:var(--coral) transparent; scrollbar-width:thin; }
.tags { display:flex; flex-wrap:wrap; gap:6px; margin-top:18px; }
.tag { color:var(--ink) !important; padding:5px 8px; background:#eee8dc; font:500 10px "DM Mono",monospace; text-transform:uppercase; }
.notice, .error-tip { margin-top:20px; padding:12px; background:var(--acid); color:var(--ink); font-size:12px; line-height:1.5; }

.examples-holder { margin-top:28px; }
.examples-holder span, .examples-holder .label-wrap { color:var(--ink) !important; }
.examples-holder .table-wrap { background:var(--paper) !important; border:1px solid var(--ink) !important; border-radius:0 !important; box-shadow:5px 5px 0 var(--ink); }
.examples-holder table { background:var(--paper) !important; }
.examples-holder thead th { color:#6c675e !important; background:#eee8dc !important; border-color:var(--ink) !important; }
.examples-holder tbody tr, .examples-holder tbody td { color:var(--ink) !important; background:var(--paper) !important; border-color:#c8c1b5 !important; }
.examples-holder tbody tr:hover td { background:var(--acid) !important; }
.examples-holder button { color:var(--ink) !important; background:transparent !important; }
.footer-note { color:#625f57 !important; margin-top:40px; text-align:center; font:500 11px/1.6 "DM Mono", monospace; opacity:1; }
.gradio-container > footer { display:none !important; }

@media (max-width: 800px) {
  .main-shell { padding:20px 14px 40px; }
  .hero { grid-template-columns:1fr; }
  .hero h1 { font-size:72px; }
  .process-strip { grid-template-columns:1fr; }
  .process-step { border-right:0; border-bottom:1px solid var(--ink); }
  .process-step:last-child { border-bottom:0; }
  .result-card { min-height:460px; height:460px; }
}
"""


def build_interface() -> gr.Blocks:
    """Construct the responsive single-page FitFindr experience."""
    with gr.Blocks(title="FitFindr", fill_width=True) as demo:
        with gr.Column(elem_classes=["main-shell"]):
            gr.HTML(
                """
                <header class="hero">
                  <div>
                    <div class="kicker">SECONDHAND, WITH A SECOND OPINION</div>
                    <h1>FIT<span>FINDR</span></h1>
                    <p class="hero-copy">Search the thrift feed, test the find against
                    your closet, and leave with a complete look worth sharing.</p>
                  </div>
                  <div class="hero-note">One request. Three tools. A planner that knows
                  when to keep going, loosen a filter, or stop.</div>
                </header>
                """
            )

            with gr.Column(elem_classes=["search-panel"]):
                with gr.Row():
                    query_input = gr.Textbox(
                        label="Describe your next find",
                        placeholder="Vintage graphic tee under $30, size M...",
                        lines=2,
                        scale=3,
                        container=True,
                    )
                    wardrobe_choice = gr.Radio(
                        choices=[
                            "Use my sample wardrobe",
                            "Start with an empty wardrobe",
                        ],
                        value="Use my sample wardrobe",
                        label="Styling context",
                        scale=2,
                    )
                submit_btn = gr.Button(
                    "SEARCH + STYLE MY FIND",
                    variant="primary",
                    elem_classes=["find-button"],
                )

            gr.HTML(
                """
                <div class="process-strip">
                  <div class="process-step">STEP 01<strong>Search listings</strong></div>
                  <div class="process-step">STEP 02<strong>Style with your closet</strong></div>
                  <div class="process-step">STEP 03<strong>Create a fit card</strong></div>
                </div>
                """
            )

            with gr.Row(elem_classes=["results-grid"], equal_height=True):
                listing_output = gr.HTML(elem_classes=["result-html"])
                outfit_output = gr.HTML(elem_classes=["result-html"])
                fitcard_output = gr.HTML(elem_classes=["result-html"])

            with gr.Column(elem_classes=["examples-holder"]):
                gr.Examples(
                    examples=EXAMPLE_QUERIES,
                    inputs=[query_input, wardrobe_choice],
                    label="QUICK STARTS",
                )

            gr.HTML(
                '<div class="footer-note">LOCAL MOCK MARKETPLACE DATA · GROQ-POWERED '
                "STYLING · GRACEFUL OFFLINE FALLBACKS</div>"
            )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    build_interface().launch(css=CSS)
