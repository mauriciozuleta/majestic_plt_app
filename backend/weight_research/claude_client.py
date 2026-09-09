"""Researches the standard net weight (in kg) of a wholesale pack/unit that
this app's price scrapers can't convert to $/kg from the source data alone
— e.g. a USA produce carton whose weight isn't stated in the scraped PDF
text, or a Colombia count-based package like "CAJA (10 per package)" with
no stated weight. One batched API call researches many items at once (via
Anthropic's server-side web_search tool), returning structured JSON rather
than prose, since this feeds a calculation, not a document a person reads.

Same API/model conventions as backend/country_profile/claude_client.py
(same key, same model, same truncation-detection approach) — see that
module's header for why max_tokens needs real headroom beyond the final
output size."""

import json
import os
import re

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'
MAX_TOKENS = 12000
# One search per item is a reasonable ceiling for "look up this pack's
# standard weight" — capped well below the API's own limits regardless.
MAX_SEARCHES_PER_ITEM = 2
MAX_ITEMS_PER_BATCH = 25


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _raise_if_truncated(data):
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError(
            "Claude's response was cut off before finishing (hit the max_tokens limit) — try again with fewer "
            'items per batch.'
        )


def _build_prompt(items):
    item_lines = '\n'.join(f'{i + 1}. {item["description"]}' for i, item in enumerate(items))
    return f"""You are researching standard net weights for wholesale produce/meat/agricultural \
packaging, for a food import/export business that needs to convert per-pack prices into $/kg for \
logistics planning and cost comparisons. Use web search to find real, verifiable standard weights — \
USDA/industry packaging standards, trade association specs, or shipping-point market news reports. \
Do not invent a plausible-sounding number if you can't find one.

For EACH item below, research the standard TOTAL net weight, in kilograms, of the described pack/unit.

Items to research:
{item_lines}

Respond with ONLY a JSON array (no markdown code fences, no commentary before or after), one object \
per item, in the same order, each shaped exactly like:
{{"index": <1-based index matching the list above>, "weight_kg": <number, or null if you genuinely \
cannot find a reliable standard for this exact pack>, "confidence": "high"|"medium"|"low", "note": \
"<one short sentence: what you found, or why you couldn't>", "sources": ["<url>", ...]}}

Rules:
- weight_kg is the TOTAL net weight of the pack/unit as described (e.g. the whole carton/box/bag),
  not a per-piece weight, unless the item description explicitly asks for a per-piece weight.
- Never invent a number — if you can't find a specific, sourced standard for this exact pack type,
  return weight_kg: null and explain why in "note".
- "sources" must be real URLs you actually used for that item, not placeholders. Omit "sources" only
  when weight_kg is null and you found nothing worth citing.
- Output ONLY the JSON array — it must parse with a standard JSON parser, nothing else in the reply.
"""


def _extract_json_array(text):
    """Claude is asked for a bare JSON array but sometimes wraps it in a
    ```json fence anyway — stripped defensively rather than trusted to
    never happen (same defensive posture as the country-profile client)."""
    stripped = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()
    return json.loads(stripped)


def research_pack_weights(items):
    """items: a list of {"signature": str, "description": str}. Returns a
    list of {"signature", "weight_kg", "confidence", "note", "sources"} in
    the same order, re-attaching each result's own signature (never trusts
    the model to echo it back verbatim)."""
    if not items:
        return []
    if len(items) > MAX_ITEMS_PER_BATCH:
        raise ValueError(f'Cannot research more than {MAX_ITEMS_PER_BATCH} items in one batch (got {len(items)})')

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': len(items) * MAX_SEARCHES_PER_ITEM}],
        'messages': [{'role': 'user', 'content': _build_prompt(items)}],
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

    text_blocks = [b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text']
    full_text = ''.join(text_blocks).strip()
    if not full_text:
        raise RuntimeError('Claude returned no text content for weight research')

    try:
        parsed = _extract_json_array(full_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Could not parse Claude\'s response as JSON: {exc}') from exc

    results = []
    for i, item in enumerate(items):
        match = next((row for row in parsed if row.get('index') == i + 1), None)
        if match is None:
            results.append(
                {
                    'signature': item['signature'],
                    'weight_kg': None,
                    'confidence': None,
                    'note': "Claude's response did not include this item.",
                    'sources': [],
                }
            )
            continue
        weight_kg = match.get('weight_kg')
        results.append(
            {
                'signature': item['signature'],
                'weight_kg': float(weight_kg) if isinstance(weight_kg, (int, float)) else None,
                'confidence': match.get('confidence'),
                'note': match.get('note'),
                'sources': match.get('sources') or [],
            }
        )
    return results
