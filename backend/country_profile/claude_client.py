"""Builds a country commercial (export/import) profile via the Claude API's
server-side web search tool — a real, live-researched document (tariffs,
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


def _build_prompt(country_name):
    return f"""You are a trade consultant briefing a client who runs a food/agricultural products \
import-export business (wholesale produce, meat, poultry, eggs, grains, seafood) on {country_name} as \
a sourcing/selling market. Use web search to research current, real information — do not rely on \
memory alone for anything tariff/tax/regulation-related, since this needs to be accurate as of today.

Write in a friendly, consultative tone — like a knowledgeable advisor briefing a client, not a dry \
legal or customs filing. Be conversational and clear while staying concrete and factual; explain why \
something matters to the client's business, not just what the rule is.

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

## Import Tariffs & Duties
Tariff/duty rates relevant to importing food/agricultural products (fresh produce, meat, poultry, \
eggs, grains, seafood) into {country_name} — cite specific rates and the product categories they \
apply to where you can find them.

## Taxes
VAT/sales tax or other taxes applied to imported food products, and any exemptions relevant to \
agricultural goods.

## Free Trade Agreements
Trade agreements {country_name} has with major partners (especially the USA, since that's this \
client's other main market) that affect tariffs or market access for food/agricultural products — \
what's covered, what isn't, and what it actually means for a supplier trying to use it.

## Seasonal Import Restrictions & Bans
Any seasonal bans, quotas, or licensing windows affecting food/agricultural imports or exports \
(e.g. to protect a domestic harvest season).

## Protected / Reserved Products
Products that are protected, subsidized, subject to import substitution policy, or otherwise given \
special domestic-industry protection that would affect a foreign supplier's ability to compete.

## Sanitary & Phytosanitary Requirements
Food safety, health certificate, or phytosanitary inspection requirements for importing the product \
categories above.

## Frequently Imported & Exported Products
A short, practical analysis of what {country_name} typically imports and exports in the food/ \
agricultural space, and what that pattern suggests about where the real opportunities or competitive \
pressure are for this client.

## Other Market Context
Anything else that helps the client understand this market — currency/repatriation rules, general \
economic conditions affecting food demand, notable recent policy shifts, logistics/infrastructure \
notes, or anything else materially relevant that doesn't fit the sections above.

## Sources
MANDATORY — this section must always be present and must never be empty. List every distinct source \
(with its URL) you used anywhere in this document, one per line as "- <title or publisher> — <URL>". \
If you used web search at all (you should have), you have sources to list here; do not skip this \
section or leave it thin.

Formatting rules:
- Every specific figure (a rate, a percentage, a date, a threshold) must be attributed to a source \
inline, e.g. "18% VAT (source: ...)".
- If you cannot find current information for a section, say so explicitly rather than guessing — \
write "No current information found for this section" rather than inventing a plausible-sounding number.
- Do not include any preamble, planning narration, or commentary about your research process (e.g. \
"I'll research...", "Let me search for...") anywhere in your reply — output ONLY the Markdown document \
itself, starting with the title line.
"""


def build_country_commercial_profile(country_name):
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': MAX_SEARCHES}],
        'messages': [{'role': 'user', 'content': _build_prompt(country_name)}],
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
    return f"""You are a trade consultant assessing whether {source_country_name}-sourced food/agricultural \
products would be competitive if sold into {target_country_name}. Write in the same friendly, consultative \
tone as a client briefing — clear and concrete, not a dry filing.

Here is {source_country_name}'s current wholesale product portfolio, summarized by category:
{summary_lines}

Here is {target_country_name}'s commercial import/export profile (tariffs, taxes, FTAs, protected products, \
seasonal restrictions) you already researched:
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


def build_competitiveness_analysis(source_country_name, category_summary, target_country_name, target_profile):
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
                'content': _build_competitiveness_prompt(source_country_name, category_summary, target_country_name, target_profile),
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
