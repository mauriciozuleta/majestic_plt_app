"""Assigns each of our own wholesale/retail products a real HS code from
Comtrade's classification reference, so the General Portfolio Directory's
reference codes mean something internationally recognized (e.g. onions from
Colombia get "CO070310") and so HS matching, Available Categories and SAM
are built on correct codes.

Two grounded Claude steps per batch of products, no keyword heuristics:

1. Heading — Claude sees the FULL list of food/agriculture headings
   (chapters 01-23, ~200 entries) and picks the 4-digit heading for each
   product from its name, category and the country it's sold in.
2. Subheading — for each chosen heading, Claude sees only that heading's
   own 6-digit subheadings and picks the most specific one that fits, or
   keeps the heading when none does.

Claude can only ever answer with a code from the list it was shown, so it
can never invent one. Earlier versions shortlisted candidates by keyword
overlap with Comtrade's wording and patched the gaps with hand-written
synonyms and product-specific prompt examples; that broke whenever a
product's name didn't share a word with its correct code ("bell pepper" vs
"fruits of the genus capsicum"), or shared one with a wrong one ("belly" ->
cured bellies, "stripped" -> tobacco). Showing the whole heading list lets
Claude's own knowledge do that mapping, guided only by the general
principles in GUIDELINES below.

Classified once per product name, ever: results are cached permanently. A
batch whose API call fails is NOT cached, so it's retried on the next
portfolio load rather than stored as "unclassifiable".
"""

import json
import os
import re

import httpx

from .. import models
from ..database import SessionLocal
from . import classification

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
# Sonnet, not Haiku: each name is classified once and cached forever, and
# the code drives HS matching, Available Categories and SAM, so accuracy is
# worth the one-time cost.
MODEL = 'claude-sonnet-5'
BATCH_SIZE = 20  # products per Claude call
MAX_FOOD_CHAPTER = 23  # chapters 01-23: food and agriculture (24 is tobacco)

GUIDELINES = """You classify food and agricultural products sold in wholesale and retail markets into official HS \
(Harmonized System) codes from UN Comtrade's classification reference.

Principles:
1. Classify what the product actually is — the commodity itself — never an ingredient, flavour, brand, packaging \
size or any other word that merely appears in its name.
2. A name may be a trade name, a cut or part name, a variety, a local or regional name, an abbreviation or a \
translation. Use the product's category and the country it is sold in to work out which commodity, species or \
animal it refers to before choosing a code. A name made of several words names one product.
3. Physical form decides between codes: fresh or chilled, frozen, dried, salted/smoked/cured, cooked, or otherwise \
prepared or preserved. Assume fresh or chilled unless the name or category indicates another form, and never choose \
a processed or preserved code for a product whose name and category don't indicate processing. A product that is \
itself a prepared food belongs under a prepared-food code. Follow each code's own wording on form: a heading that \
names a product without stating a form covers it fresh or dried, while a code that says "dried, crushed or ground" \
does not cover the same plant sold fresh — that belongs under the fresh vegetable codes.
4. Answer only with a code from the list you are given. If none genuinely describes the product, answer null — never \
the closest-sounding code."""

_headings_cache: list[dict] | None = None


def _headings() -> list[dict]:
    global _headings_cache
    if _headings_cache is None:
        _headings_cache = [
            entry
            for entry in classification.list_searchable_hs_codes()
            if entry['level'] == 4 and int(entry['chapter']) <= MAX_FOOD_CHAPTER
        ]
    return _headings_cache


def _subheadings(heading: str) -> list[dict]:
    return [entry for entry in classification.list_searchable_hs_codes() if entry['level'] == 6 and entry['hs_code'].startswith(heading)]


def _api_key() -> str | None:
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _product_line(index: int, name: str, context: str) -> str:
    return f'{index}. "{name}"' + (f' — {context}' if context else '')


def _ask(system_blocks: list[dict], user_text: str) -> list[dict]:
    """One Claude call that must answer with a JSON array. Raises on any API
    or parsing failure — callers must never cache a failure as an answer."""
    api_key = _api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (CLAUDE_API_KEY).')
    response = httpx.post(
        ANTHROPIC_API_URL,
        headers={'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'},
        json={'model': MODEL, 'max_tokens': 4000, 'system': system_blocks, 'messages': [{'role': 'user', 'content': user_text}]},
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'Claude API error {response.status_code}: {response.text[:300]}')
    text = ''.join(b.get('text', '') for b in response.json().get('content', []) if b.get('type') == 'text')
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise RuntimeError("Claude's classification reply contained no JSON array.")
    rows = json.loads(match.group(0))
    if not isinstance(rows, list):
        raise RuntimeError("Claude's classification reply was not a JSON array.")
    return rows


def _answers_by_index(rows: list[dict], count: int, field: str) -> list:
    answers = [None] * count
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get('index'), int) and 1 <= row['index'] <= count:
            answers[row['index'] - 1] = row.get(field)
    return answers


def _choose_headings(products: list[tuple[str, str]]) -> list[str | None]:
    """products: [(name, context)] -> the 4-digit heading for each, or None."""
    heading_list = '\n'.join(f'{entry["hs_code"]}: {entry["description"]}' for entry in _headings())
    system = [
        {'type': 'text', 'text': GUIDELINES},
        # The heading list is identical on every call — cached, so a long
        # classification job pays for it once.
        {'type': 'text', 'text': f'HS headings you may choose from:\n{heading_list}', 'cache_control': {'type': 'ephemeral'}},
    ]
    lines = '\n'.join(_product_line(i, name, context) for i, (name, context) in enumerate(products, start=1))
    user = f"""Choose the HS heading (4 digits) for each product below.

Products:
{lines}

Return ONLY a JSON array, one entry per product: [{{"index": <number>, "heading": "<4-digit code from the list>" or null}}]"""
    valid = {entry['hs_code'] for entry in _headings()}
    return [code if code in valid else None for code in _answers_by_index(_ask(system, user), len(products), 'heading')]


def _choose_subheadings(products: list[tuple[str, str, str, list[dict]]]) -> list[str]:
    """products: [(name, context, heading, subheadings)] -> the most specific
    code for each: one of its subheadings, or the heading itself."""
    blocks = []
    for i, (name, context, heading, options) in enumerate(products, start=1):
        listed = '\n'.join(f'   - {entry["hs_code"]}: {entry["description"]}' for entry in options)
        blocks.append(f'{_product_line(i, name, context)}\n   Heading {heading}: {classification.hs_name(heading)}\n   Subheadings:\n{listed}')
    user = f"""Each product below has already been placed in an HS heading. Choose the most specific subheading that \
correctly describes it. If none of the subheadings fits, answer with the heading itself.

{chr(10).join(blocks)}

Return ONLY a JSON array, one entry per product: [{{"index": <number>, "hs_code": "<a listed subheading, or the heading>"}}]"""
    answers = _answers_by_index(_ask([{'type': 'text', 'text': GUIDELINES}], user), len(products), 'hs_code')
    results = []
    for (_name, _context, heading, options), code in zip(products, answers):
        valid = {entry['hs_code'] for entry in options} | {heading}
        results.append(code if code in valid else heading)
    return results


def classify_products(products: list[tuple[str, str]]) -> list[str | None]:
    """products: [(name, context)] -> an HS code (6- or 4-digit) or None per
    product, in order. Raises if a Claude call fails."""
    headings = _choose_headings(products)
    pending = [(i, name, context, heading, _subheadings(heading)) for i, ((name, context), heading) in enumerate(zip(products, headings)) if heading]
    codes: list[str | None] = list(headings)
    with_options = [item for item in pending if item[4]]
    if with_options:
        chosen = _choose_subheadings([(name, context, heading, options) for _, name, context, heading, options in with_options])
        for (i, *_rest), code in zip(with_options, chosen):
            codes[i] = code
    return codes


def get_cached(db) -> dict[str, dict | None]:
    """Every product already classified, ever — {product_key: {hs_code,
    description} | None}. Instant: no live matching or Claude calls, just a
    table read, same shape as weight_research.list_weight_research()."""
    return {
        row.product_key: ({'hs_code': row.hs_code, 'description': row.description} if row.hs_code else None)
        for row in db.query(models.ProductHsCode).all()
    }


def run_classification_job(items: list[dict]) -> None:
    """The slow path: classifies every item not already cached and persists
    the results. Meant to run as a FastAPI BackgroundTask (see
    routers/product_classification.py) — opens its own DB session because a
    request-scoped one closes the moment the triggering request returns.
    `items` is [{key, name, context}] (context: category and country); a key
    already cached is skipped (checked again here in case two requests raced
    to start a job for overlapping items)."""
    db = SessionLocal()
    try:
        existing_keys = {
            key for (key,) in db.query(models.ProductHsCode.product_key).filter(models.ProductHsCode.product_key.in_([i['key'] for i in items]))
        }
        to_classify = [item for item in items if item['key'] not in existing_keys]
        failure = None
        for start in range(0, len(to_classify), BATCH_SIZE):
            batch = to_classify[start : start + BATCH_SIZE]
            try:
                codes = classify_products([(item['name'], item.get('context') or '') for item in batch])
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                failure = exc
                continue
            # A real null answer (nothing in the food chapters fits) is cached
            # too, so it isn't retried forever; a failed call never is.
            for item, code in zip(batch, codes):
                db.add(models.ProductHsCode(product_key=item['key'], hs_code=code, description=classification.hs_name(code) if code else None))
            db.commit()
        if failure:
            raise RuntimeError(f'Some products could not be classified and will be retried: {failure}')
    finally:
        db.close()
