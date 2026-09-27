"""Estimates the typical TOTAL net weight (in grams) of one count-based
priced unit/pack — e.g. Trinidad's "papaya, box of 18" style packaging —
for Market Opportunities' count-vs-weight conversion (see
src/components/company/tabs/OperationsTab/MarketAnalysis/
countWeightConversion.js).

Deliberately NOT weight_research/claude_client.py: that module calls
claude-sonnet-5 WITH the server-side web_search tool, batched, backed by
models.ProductWeightResearch — a real, capable, but comparatively expensive
research call, already wired up for a different purpose (USA produce
cartons / Colombia's own single-country $/kg table, via
usaWeightResearchItem/colombiaWeightResearchItem). Reusing that pathway
here would defeat the point of this one: this is a single, short, CHEAP
Haiku call per distinct product, no web search, no tool use at all — a
plain "what's the typical weight of one X" estimate from the model's own
general knowledge, not a sourced research finding. Same API/key/model-id
conventions as backend/knowledge_base/claude_client.py (same
CLAUDE_API_KEY/claude_api_key env var, same endpoint), just pointed at
Haiku instead of Sonnet."""

import json
import os
import re

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-haiku-4-5'
MAX_TOKENS = 4000
MAX_ITEMS_PER_BATCH = 25


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _build_prompt(items):
    item_lines = '\n'.join(f'{i + 1}. {item["description"]}' for i, item in enumerate(items))
    return f"""For EACH item below, give your best estimate of the typical TOTAL net weight, in grams, of ONE \
described priced unit/pack of a wholesale/retail produce, meat, or grocery product. Use your general knowledge — \
no research needed, just a reasonable typical estimate. If a description genuinely gives you nothing to estimate \
from, return null rather than guessing wildly.

Items to estimate:
{item_lines}

Respond with ONLY a JSON array (no markdown code fences, no commentary before or after), one object per item, in \
the same order, each shaped exactly like:
{{"index": <1-based index matching the list above>, "weight_grams": <number, or null if you genuinely cannot \
estimate this>, "note": "<one short sentence explaining the estimate>"}}

Output ONLY the JSON array — it must parse with a standard JSON parser, nothing else in the reply.
"""


def _extract_json_array(text):
    stripped = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()
    return json.loads(stripped)


def estimate_unit_weights(items):
    """items: a list of {"signature": str, "description": str}. Returns a
    list of {"signature", "weight_grams", "note"} in the same order,
    re-attaching each result's own signature (never trusts the model to
    echo it back verbatim)."""
    if not items:
        return []
    if len(items) > MAX_ITEMS_PER_BATCH:
        raise ValueError(f'Cannot estimate more than {MAX_ITEMS_PER_BATCH} items in one batch (got {len(items)})')

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'messages': [{'role': 'user', 'content': _build_prompt(items)}],
    }
    headers = {
        'x-api-key': api_key,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }

    response = httpx.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    data = response.json()
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError("Claude's response was cut off before finishing — try again with fewer items per batch.")

    text_blocks = [b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text']
    full_text = ''.join(text_blocks).strip()
    if not full_text:
        raise RuntimeError('Claude returned no text content for unit weight estimation')

    try:
        parsed = _extract_json_array(full_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse Claude's response as JSON: {exc}") from exc

    results = []
    for i, item in enumerate(items):
        match = next((row for row in parsed if row.get('index') == i + 1), None)
        if match is None:
            results.append({'signature': item['signature'], 'weight_grams': None, 'note': "Claude's response did not include this item."})
            continue
        weight_grams = match.get('weight_grams')
        results.append(
            {
                'signature': item['signature'],
                'weight_grams': float(weight_grams) if isinstance(weight_grams, (int, float)) else None,
                'note': match.get('note'),
            }
        )
    return results
