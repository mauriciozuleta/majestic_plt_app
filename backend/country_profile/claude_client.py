"""Builds a country commercial (export/import) profile — from the country's
official Country Commercial Guide when it has one (see
trade_gov/commercial_guides.py), and/or the Claude API's server-side web
search tool — a real, live-researched document (tariffs,
taxes, seasonal bans, protected products, free trade agreements, sanitary/
phytosanitary rules, frequently traded products), not a static/canned
template. One API call handles the whole search-then-write loop
server-side (Anthropic's web_search tool runs multiple searches within a
single request/response when needed).

This is AI-researched, not a customs authority's own publication — the
generated document notes that plainly. The API key is read server-side
only, from CLAUDE_API_KEY (or the lowercase `claude_api_key`, however it's
actually named in .env)."""

import os
import re

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'
# `max_tokens` caps ALL output for the turn, not just the final text — the
# search tool's own tool_use/tool_result blocks count against it too, so
# with up to MAX_SEARCHES searches this budget needs real headroom beyond
# just "how long is the document." The original 8000 was not enough: every
# profile built under it was cut off mid-document with no Sources section
# at all, since Sources is the last section requested and never got
# reached once the budget ran out.
MAX_TOKENS = 16000
# A guide-based profile is longer (Opportunities for Our Products, a fuller
# Import Rules section) — 16000 cut the first one off before its Sources.
MAX_TOKENS_WITH_GUIDE = 32000
# Seconds: a 32k-token document takes well over the old 300 to write.
REQUEST_TIMEOUT = 600
MAX_SEARCHES = 10


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _raise_if_truncated(data):
    """A response cut off by hitting max_tokens comes back with
    stop_reason == 'max_tokens' — the document is mid-sentence and never
    reaches its Sources section (the last one requested). This used to
    fail silently: every real profile built under the old 8000-token
    budget shipped this way. Failing loudly here means a too-small budget
    surfaces as a build error instead of a document quietly missing its
    citations."""
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError(
            "Claude's response was cut off before finishing (hit the max_tokens limit) — the document would be "
            'incomplete and missing its Sources section. Try again; if this keeps happening, the token budget needs raising.'
        )


# With an official Country Commercial Guide the profile is grounded in it, so
# far fewer searches are needed — only for gaps and figures that may have changed.
MAX_SEARCHES_WITH_GUIDE = 5


def _guide_section(country_name, guide):
    if not guide:
        return ''
    chapters = '\n\n'.join(f"<<< {chapter['title']} — {chapter['url']} >>>\n{chapter['text']}" for chapter in guide['chapters'])
    published = f" (last published {guide['published']})" if guide.get('published') else ''
    return f"""
OFFICIAL SOURCE — the U.S. Commercial Service's Country Commercial Guide for {country_name}{published}, written at \
the U.S. Embassy. These are its chapters on the market, opportunities and import rules. Treat it as our primary \
source: base every section on it first and cite it inline as "(source: Country Commercial Guide — <chapter \
title>)". Use web search only for what the guide doesn't cover, or to check a figure that may have changed since it \
was published — and say when a search result differs from the guide. The guide is written for U.S. exporters: \
where a rule or opportunity is specific to U.S. goods (a U.S. trade agreement, U.S. certificates), say so plainly \
and say what applies to goods from our other source countries when the guide or a search shows it.

{chapters}
"""


def _products_section(country_name, our_products):
    if not our_products:
        return ''
    lines = '\n'.join(f'- {line}' for line in our_products['lines'])
    return f"""
OUR PRODUCTS FOR {country_name} — {our_products['basis']}:
{lines}
"""


def _build_prompt(country_name, guide=None, our_products=None):
    opportunities = (
        f"""For the products listed above under OUR PRODUCTS (group them by kind — vegetables, fruit, meat, ...): what \
{country_name}'s demand for them looks like, whether the market relies on imports for them, which sectors or \
buyers are the real opening (retail, tourism/hotels, food processing, ...), and anything that helps or blocks \
each one in particular (a tariff, a permit, a ban, local-industry protection). Be concrete about which of our \
products look strongest and which look weakest there, and why. Where neither the guide nor a search says \
anything about a product, say so rather than guessing."""
        if our_products
        else f"""Which fresh food and agricultural products (produce, meat, poultry, eggs, grains, seafood) have the \
clearest demand in {country_name}, whether the market relies on imports for them, and which sectors or buyers \
are the real opening (retail, tourism/hotels, food processing, ...)."""
    )
    return f"""We run a food/agricultural products import-export business (wholesale produce, meat, poultry, \
eggs, grains, seafood). You are a member of our own team, writing our internal briefing on {country_name} as a \
sourcing/selling market for us. {"Work from the official guide below first; use" if guide else "Use"} web search \
for current, real information — do not rely on memory alone for anything tariff/tax/regulation-related, since \
this needs to be accurate as of today.
{_guide_section(country_name, guide)}{_products_section(country_name, our_products)}
Voice: write in the first person plural — "we", "our", "us" — as the company itself, never about "the client" \
or "the company" in the third person (for example "what this means for us", "our other main market", "if we \
want to export there"). Keep a friendly, conversational tone, clear and concrete rather than a dry legal or \
customs filing, and explain why each point matters to our business, not just what the rule is.

Write a Markdown document titled "# {country_name} — Commercial Import/Export Profile" with EXACTLY \
this section order:

## Quick Facts
A short bulleted list of the handful of numbers/facts that matter most at a glance. Use this exact \
"- Label: Value" format, one per line, plain text only — no bold/markdown emphasis, no sub-bullets or \
extra commentary on these lines:
- Average food-import tariff: <rate or range>
- VAT / sales tax on food imports: <rate>
- Free trade agreement with the USA: <Yes/No — one-line detail>
- Seasonal import restrictions: <Yes/No — one-line detail>
- Top imported food products: <2-4 products>
- Top exported food products: <2-4 products>
If you genuinely cannot find a figure for one of these, write "Not found" as its value rather than \
guessing.

## Opportunities for Our Products
{opportunities}

## Import Rules for Food
Everything that governs getting fresh food and agricultural products (produce, meat, poultry, eggs, grains, \
seafood) into {country_name}, under these sub-headings:
### Tariffs & Duties
Rates and the product categories they apply to, including any regional common tariff (e.g. CARICOM's CET) and \
how goods from inside vs. outside a trade bloc are treated.
### Taxes
VAT/GCT/sales tax or other taxes on imported food, and exemptions for agricultural goods.
### Import Permits, Licences & Documents
Which of our product categories need an import permit or licence, from which agency, and the documents a \
shipment needs.
### Labeling & Standards
Labeling/marking rules and standards (and the body that enforces them) that apply to food we'd sell there.
### Prohibited & Restricted Products
Food/agricultural items that are banned or restricted, and from where.
### Sanitary & Phytosanitary Requirements
Health certificates, phytosanitary certificates and inspections for the product categories above.

## Free Trade Agreements
Trade agreements {country_name} has with major partners (especially the USA, since that's our \
other main market) that affect tariffs or market access for food/agricultural products — \
what's covered, what isn't, and what it actually means for a supplier trying to use it.

## Seasonal Import Restrictions & Bans
Any seasonal bans, quotas, or licensing windows affecting food/agricultural imports or exports \
(e.g. to protect a domestic harvest season).

## Protected / Reserved Products
Products that are protected, subsidized, subject to import substitution policy, or otherwise given \
special domestic-industry protection that would affect a foreign supplier's ability to compete.

## Frequently Imported & Exported Products
A short, practical analysis of what {country_name} typically imports and exports in the food/ \
agricultural space, and what that pattern suggests about where the real opportunities or competitive \
pressure are for us.

## Other Market Context
Anything else that helps us understand this market — currency/repatriation rules, general \
economic conditions affecting food demand, notable recent policy shifts, logistics/infrastructure \
notes, or anything else materially relevant that doesn't fit the sections above.

## Sources
MANDATORY — this section must always be present and must never be empty. List every distinct source \
(with its URL) you used anywhere in this document, one per line as "- <title or publisher> — <URL>"\
{" — starting with each Country Commercial Guide chapter you drew on" if guide else ""}.

Formatting rules:
- Every specific figure (a rate, a percentage, a date, a threshold) must be attributed to a source \
inline, e.g. "18% VAT (source: ...)".
- If you cannot find current information for a section, say so explicitly rather than guessing — \
write "No current information found for this section" rather than inventing a plausible-sounding number.
- Do not include any preamble, planning narration, or commentary about your research process (e.g. \
"I'll research...", "Let me search for...") anywhere in your reply — output ONLY the Markdown document \
itself, starting with the title line.
"""


def build_country_commercial_profile(country_name, extra_prompt='', guide=None, our_products=None):
    """`guide`: the country's Country Commercial Guide chapters
    (trade_gov/commercial_guides.py), the profile's primary source when the
    country has one. `our_products`: {basis, lines} — our products for this
    market from Market Opportunities, for the Opportunities section."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS_WITH_GUIDE if guide else MAX_TOKENS,
        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': MAX_SEARCHES_WITH_GUIDE if guide else MAX_SEARCHES}],
        'messages': [{'role': 'user', 'content': _build_prompt(country_name, guide, our_products) + extra_prompt}],
    }
    headers = {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }

    response = httpx.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    _raise_if_truncated(data)

    body = _join_text_blocks(data.get('content', []))
    body = _strip_preamble(body)
    if not body:
        raise RuntimeError('Claude returned no text content for the profile')

    return body


def _join_text_blocks(content_blocks):
    """Citation-attributed spans come back as their own text block, split
    out of the middle of what's really one sentence/bullet — e.g. a bullet
    like "- Beef is subject to an 80% duty." arrives as three blocks: "- ",
    "Beef is subject to an 80% duty.", "". Blindly joining blocks with a
    blank-line separator (or trusting each block's own leading/trailing
    newlines) turns those citation splits into large gaps mid-sentence.
    A block that's genuinely a new structural element (heading/bullet/
    blockquote) starts with '#', '-'/'*', or '>' once trimmed — those get
    their own line; everything else is assumed to continue the current
    line and is joined with a single space."""
    pieces = []
    for block in content_blocks:
        if block.get('type') != 'text':
            continue
        text = block.get('text', '').strip()
        if not text:
            continue
        if pieces and re.match(r'^[#\-*>]', text):
            pieces.append('\n\n' + text)
        elif pieces:
            pieces.append(' ' + text)
        else:
            pieces.append(text)
    return re.sub(r'\n{3,}', '\n\n', ''.join(pieces)).strip()


def _strip_preamble(body):
    """Despite the prompt's instruction, Claude sometimes still narrates
    its research plan before the actual document ("I'll research...",
    "I now have substantial material...") — that text arrives as ordinary
    text blocks indistinguishable from the document itself, so it has to
    be cut on the output side: find the real title line and drop
    everything before it."""
    match = re.search(r'^# .+$', body, re.MULTILINE)
    return body[match.start():] if match else body


QUICK_FACTS_SECTION = re.compile(r'## Quick Facts\s*\n(.*?)(?=\n## |\Z)', re.DOTALL)
QUICK_FACT_LINE = re.compile(r'^- ([^:]+):\s*(.+)$', re.MULTILINE)


def _strip_markdown_emphasis(text):
    # A plain .replace, not a paired \*\*(.+?)\*\* regex — Claude sometimes
    # bolds "Label : Value." as one unit before continuing in prose, so the
    # closing ** can land in the value half of an already-split label/value
    # pair, leaving no complete pair in either half individually.
    return text.replace('**', '').strip()


def extract_quick_facts(body):
    """Pulls the "## Quick Facts" bullet list out as [{label, value}], for
    the dashboard tiles — parsed from the same document a person reads in
    the full view, not a second model call. Despite the prompt asking for
    plain "- Label: Value" lines, Claude sometimes bolds the label anyway
    ("- **Label:** Value") — stripped defensively rather than trusted to
    never happen."""
    section_match = QUICK_FACTS_SECTION.search(body)
    if not section_match:
        return []
    return [
        {'label': _strip_markdown_emphasis(label), 'value': _strip_markdown_emphasis(value)}
        for label, value in QUICK_FACT_LINE.findall(section_match.group(1))
    ]


def _build_competitiveness_prompt(source_country_name, category_summary, target_country_name, target_profile):
    summary_lines = '\n'.join(
        f"- {row['category']}: avg price {row['avg_price']} {row['unit']}, {row['product_count']} products "
        f"(examples: {', '.join(row['sample_products'][:5])})"
        for row in category_summary
    )
    return f"""We run a food/agricultural import-export business. You are a member of our own team, writing our \
internal assessment of whether the {source_country_name}-sourced food/agricultural products we handle would be \
competitive if we sold them into {target_country_name}.

Voice: write in the first person plural — "we", "our", "us" — as the company itself, never about "the client" \
or "the company" in the third person (for example "our {source_country_name} products", "we would be priced \
out", "we could compete"). Keep a friendly, conversational tone, clear and concrete rather than a dry filing.

Here is our current {source_country_name} wholesale product portfolio, summarized by category:
{summary_lines}

Here is our own commercial import/export profile of {target_country_name} (tariffs, taxes, FTAs, protected \
products, seasonal restrictions), which we already researched:
---
{target_profile}
---

You may use web search for anything not already covered above (e.g. current {target_country_name} wholesale/ \
retail price benchmarks for these same categories, to compare against). Use it if it would materially improve \
the assessment.

Write a Markdown document titled "# {source_country_name} → {target_country_name} — Product Competitiveness \
Analysis" with this structure:

## Quick Facts
Use this exact "- Label: Value" format, one per line, plain text only — no bold/markdown emphasis \
anywhere in this section, and keep each value to one short line:
- Most competitive category: <category — brief why>
- Least competitive category: <category — brief why>
- Categories blocked or restricted: <list, or "None found">
- Overall competitiveness: <High/Medium/Low — brief why>

## Category-by-Category Assessment
For each category in the portfolio above, a short paragraph covering: does {target_country_name}'s tariff/tax \
treatment for this category make {source_country_name} product price-competitive there once landed; does any \
protected-product, seasonal-restriction, or FTA rule from the profile above help or hurt this category \
specifically; and an overall verdict (Competitive / Competitive with caveats / Not competitive) for that category.

## Sources
MANDATORY if you used web search — list every source (with URL) you used beyond the profile already provided.

Formatting rules:
- Every claim about a tariff, tax, or restriction must trace back to the profile provided above or a cited \
source — do not invent figures.
- Output ONLY the Markdown document, starting with the title line — no preamble or research narration.
"""


def build_competitiveness_analysis(source_country_name, category_summary, target_country_name, target_profile, extra_prompt=''):
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 5}],
        'messages': [
            {
                'role': 'user',
                'content': _build_competitiveness_prompt(source_country_name, category_summary, target_country_name, target_profile) + extra_prompt,
            }
        ],
    }
    headers = {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }

    response = httpx.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=300)
    response.raise_for_status()
    data = response.json()
    _raise_if_truncated(data)

    body = _strip_preamble(_join_text_blocks(data.get('content', [])))
    if not body:
        raise RuntimeError('Claude returned no text content for the competitiveness analysis')

    return body
