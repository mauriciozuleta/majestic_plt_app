"""Claude Haiku judgement of which target-market products are the SAME product
as each source product, for Market Opportunities' AI match tier — the tier
that runs only after exact-name, curated-override and shared-HS-code matching
found nothing. Needed because HS codes alone miss real matches: one side
classified to a 4-digit heading and the other to a 6-digit subheading, or one
side misclassified (USDA's fresh "Primal Belly" coded as cured belly 021012
while Jamaica's fresh "Pork Bellies" is 020319).

Same API/key/model conventions as unit_weight_estimates/claude_client.py: one
short Haiku call, no tools, no web search. The model may only answer with
names copied from the candidate list; anything else is discarded."""

import json
import os
import re

import httpx

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
# Sonnet, not Haiku: the prompt states general principles only (no named
# products), so the judge must supply trade knowledge itself — e.g. which
# retail cuts come from which wholesale primal. Haiku applied those rules
# noticeably less well. Every judgement is cached, so the cost is one-off.
MODEL = 'claude-sonnet-5'
MAX_TOKENS = 16000
MAX_SOURCES_PER_BATCH = 10
# Part of every cache signature (see routers/product_matches.py): bumping it
# re-judges everything instead of reusing answers from an older prompt.
PROMPT_VERSION = 'v5'


def _get_api_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _build_prompt(sources, candidates, target_country):
    source_lines = '\n'.join(f'{i + 1}. {source}' for i, source in enumerate(sources))
    candidate_lines = '\n'.join(f'- {name}' for name in candidates)
    return f"""You are matching agricultural and food products between two markets for a price comparison. For EACH \
source product below, pick the products from the {target_country} list that are the SAME product, so their prices \
per kg can fairly be compared.

Product names come from different countries' price reports: they may be trade names, cut or part names, varieties, \
local or regional names, abbreviations or translations. First work out what each product actually is — its species \
and, for meat and fish, which part or cut — using its category and source; then compare on that, not on shared words.

Count as the same product:
- the same species AND the same part, cut or type, whatever each market calls it — including the different trade \
or regional names the same cut or produce goes by
- a wholesale primal or bulk cut and a retail cut taken from that same primal — the comparison is often wholesale \
against retail, so that difference is expected
- differences in variety within the same species and type, size or quality grade, ripeness stage, origin label \
(local/imported), brand or packaging
- fresh/chilled vs frozen, ONLY if nothing in the list matches the exact form

Do NOT count as the same product:
- a different species, even one with a similar name or look
- a different part or cut of the same animal, unless one is the primal the other is cut from
- fresh vs cured/smoked/salted/dried, or raw vs prepared/processed
- a whole carcass or whole bird vs a single cut

An empty list is the correct answer whenever the list has no product of the same species, part and form. Never pick \
the "closest available" item.

Source products:
{source_lines}

{target_country} products (copy names EXACTLY as written here):
{candidate_lines}

Respond with ONLY a JSON array (no markdown fences, no commentary), one object per source product, in order:
{{"index": <1-based source index>, "source_species": "<scientific name of the source product's species, e.g. \
Sus scrofa domesticus>", "matches": [{{"name": "<exact name from the {target_country} list>", "species": \
"<scientific name of that product's species>"}}], "note": "<one short sentence explaining the match or why there \
is none>"}}
Use "matches": [] when nothing in the list is the same product.
"""


def _extract_json_array(text):
    stripped = text.strip()
    fence_match = re.match(r'^```(?:json)?\s*(.*?)\s*```$', stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()
    return json.loads(stripped)


def judge_matches(sources, candidates, target_country):
    """sources: list of source-product descriptions (name plus context).
    candidates: list of distinct target product names. Returns a list, in
    source order, of {"matches": [candidate names], "note": str}; only names
    that appear verbatim in `candidates` survive."""
    if not sources:
        return []
    if len(sources) > MAX_SOURCES_PER_BATCH:
        raise ValueError(f'Cannot judge more than {MAX_SOURCES_PER_BATCH} source products in one batch (got {len(sources)})')

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (set claude_api_key in the backend .env file)')

    response = httpx.post(
        ANTHROPIC_API_URL,
        json={
            'model': MODEL,
            'max_tokens': MAX_TOKENS,
            'messages': [{'role': 'user', 'content': _build_prompt(sources, candidates, target_country)}],
        },
        headers={'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if data.get('stop_reason') == 'max_tokens':
        raise RuntimeError("Claude's response was cut off before finishing — try again with fewer products per batch.")

    text = ''.join(block.get('text', '') for block in data.get('content', []) if block.get('type') == 'text').strip()
    if not text:
        raise RuntimeError('Claude returned no text content for product matching')
    try:
        parsed = _extract_json_array(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse Claude's response as JSON: {exc}") from exc

    # The prompt asks for a bare array, but a reply wrapped in an object
    # ({"results": [...]}) is taken too, and anything in it that isn't a
    # product object is ignored — iterating a dict yields its string keys,
    # which used to fail the whole batch ("'str' object has no attribute 'get'").
    if isinstance(parsed, dict):
        parsed = next((value for value in parsed.values() if isinstance(value, list)), [])
    rows_by_index = {}
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            rows_by_index.setdefault(int(item.get('index')), item)
        except (TypeError, ValueError):
            continue

    allowed = set(candidates)
    results = []
    for i in range(len(sources)):
        row = rows_by_index.get(i + 1)
        if row is None:
            results.append({'matches': [], 'note': "Claude's response did not include this product."})
            continue
        source_species = _species_key(row.get('source_species'))
        matches, rejected = [], []
        for match in row.get('matches') or []:
            name = match.get('name') if isinstance(match, dict) else match
            if not isinstance(name, str) or name not in allowed:
                continue
            species = _species_key(match.get('species')) if isinstance(match, dict) else None
            # Enforced here rather than trusted to the prompt: a stated species
            # that differs from the source's is never the same product.
            if source_species and species and species != source_species:
                rejected.append(name)
                continue
            matches.append(name)
        note = row.get('note') or ''
        if rejected:
            note = f'{note} (Rejected as a different species: {", ".join(rejected)}.)'.strip()
        results.append({'matches': list(dict.fromkeys(matches)), 'note': note})
    return results


def _species_key(value):
    """Genus + species, lowercased ("Sus scrofa domesticus" -> "sus scrofa"),
    so a subspecies or author suffix doesn't count as a different species."""
    if not isinstance(value, str):
        return None
    words = re.findall(r'[a-z]+', value.lower())
    return ' '.join(words[:2]) if len(words) >= 2 else None
