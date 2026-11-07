"""Web research of the weight of ONE item of a product, through Anthropic's server-side web_search tool (same key, endpoint and model conventions as
backend/weight_research/claude_client.py). One batched call researches several products; the answer is structured JSON because it feeds a
calculation. Nothing is invented: a product with no reliable source comes back with `item_kg = None` and the reason."""

import json
import os
import re

import httpx

from .store import ItemWeight

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'
MAX_TOKENS = 16000
MAX_ITEMS_PER_BATCH = 12
SEARCHES_PER_ITEM = 2

UNIT_WORDS = {
    'each': 'one single whole item',
    'bunch': 'one retail bunch/bundle as sold in a supermarket',
    'head': 'one whole head',
    'sleeve': 'one sleeve as sold',
    'dozen': 'one dozen',
    'pack': 'one retail pack/bag/clamshell with that count',
}


def _api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _prompt(items: list[tuple[str, str, str]]) -> str:
    lines = '\n'.join(f'{i + 1}. "{name}" — the priced unit is "{unit}" ({UNIT_WORDS.get(unit, unit)})' for i, (name, unit, _hint) in enumerate(items))
    return f"""You are researching typical weights of fresh/packaged food items for a food import/export business that must convert between a COUNT of items and a WEIGHT in kilograms, in both directions (price per item -> price per kg, and "how many items fit in a 10 kg box").

Use web search to find real, verifiable figures: USDA / FAO / national standards, produce-industry packing specifications, grower or marketing-board sites, supermarket product pages. Prefer a figure for the item as SOLD (whole, unpeeled, uncooked) unless the item says otherwise. Do not invent a number you cannot support.

For EACH product below research:
- item_kg: the TYPICAL (average) weight in kilograms of ONE item of the unit described;
- item_kg_min / item_kg_max: the usual range in kilograms for one item;
- std_pack_kg and std_pack_items: if the trade has a STANDARD wholesale carton/box for this product, its net weight in kg and the usual item count in it (otherwise null).

Products:
{lines}

Respond with ONLY a JSON array (no code fences, no text before or after), one object per product, in order:
{{"index": <1-based>, "item_kg": <number or null>, "item_kg_min": <number or null>, "item_kg_max": <number or null>, "std_pack_kg": <number or null>, "std_pack_items": <number or null>, "confidence": "high"|"medium"|"low", "note": "<one short sentence: what the figure is based on, or why none was found>", "sources": ["<url you actually used>", ...]}}

Rules: kilograms, not grams; if you cannot find a reliable figure return item_kg null and say why in note; sources must be real URLs you used."""


def _json_array(text: str):
    stripped = text.strip()
    fenced = re.match(r'^```(?:json)?\s*(.*?)\s*```$', stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start, end = stripped.find('['), stripped.rfind(']')
    return json.loads(stripped[start : end + 1] if start != -1 and end != -1 else stripped)


def research_item_weights(items: list[tuple[str, str, str]]) -> list[ItemWeight]:
    """items: [(product name, count unit, hint)] -> one ItemWeight per item, same order. `hint` is free text (e.g. the original unit string)."""
    if not items:
        return []
    if len(items) > MAX_ITEMS_PER_BATCH:
        raise ValueError(f'At most {MAX_ITEMS_PER_BATCH} products per research call (got {len(items)}).')
    key = _api_key()
    if not key:
        raise RuntimeError('No Claude API key configured (set CLAUDE_API_KEY in the backend .env file).')
    payload = {
        'model': MODEL,
        'max_tokens': MAX_TOKENS,
        'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': len(items) * SEARCHES_PER_ITEM}],
        'messages': [{'role': 'user', 'content': _prompt(items)}],
    }
    response = httpx.post(ANTHROPIC_API_URL, json=payload, headers={'x-api-key': key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'}, timeout=900)
    response.raise_for_status()
    data = response.json()
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError('The research answer was cut off (max_tokens) — use fewer products per call.')
    text = ''.join(block.get('text', '') for block in data.get('content', []) if block.get('type') == 'text')
    if not text.strip():
        raise RuntimeError('The research call returned no text.')
    parsed = _json_array(text)
    results = []
    for index, (name, unit, _hint) in enumerate(items):
        row = next((entry for entry in parsed if entry.get('index') == index + 1), None)
        if row is None:
            results.append(ItemWeight(name, unit, None, note="The research answer did not include this product."))
            continue
        number = lambda key_: float(row[key_]) if isinstance(row.get(key_), (int, float)) and row[key_] > 0 else None  # noqa: E731
        results.append(ItemWeight(name, unit, number('item_kg'), number('item_kg_min'), number('item_kg_max'), number('std_pack_kg'), number('std_pack_items'),
                                  row.get('confidence'), str(row.get('note') or ''), [str(url) for url in row.get('sources') or []]))
    return results
