"""Assigns each of our own wholesale-market products a real HS code from
Comtrade's classification reference, so the General Portfolio Directory's
reference codes mean something internationally recognized (e.g. onions from
Colombia get "CO070310", not an arbitrary sequence number) instead of the
old scheme.

Matching a messy real-world product name ("White Onion", "Reina Mango",
"Cebolla Cabezona Roja" already translated) against ~1,400 official HS
descriptions is not reliable by keyword overlap alone — Comtrade's own
descriptions are full of color/size words ("black, white or red currants",
"red salmon") that collide with a product's own color/grade words and
produce confident-looking but wrong matches (confirmed while building this:
plain keyword scoring alone matched "White Onion" to a currant/gooseberry
entry and "Red Onion" to frozen salmon, purely on the word "white"/"red").

So this is two stages: a cheap, deterministic SHORTLIST (keyword overlap,
weighted so each description's own primary subject — the phrase right
after its first semicolon, which is consistently "<broad group>; <specific
name>, <qualifiers>" across the whole reference — counts far more than
incidental color/grade words), then Claude picks the single best code from
that shortlist per product (or says none fit) — grounded so it can never
invent a code that isn't real, but able to actually understand that "White
Onion" is an onion, not a currant. Classified once per product name, ever:
results are cached permanently (products/prices change constantly; what
counts as "an onion" does not), so this never re-runs, and never re-spends
an API call, for a name already seen.
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
# Sonnet, not Haiku: an audit of 770 cached codes found Haiku choosing
# frozen over fresh chicken cuts, bananas for "Banana Passionfruit" and
# coconut for Jamaican "coco" (cocoyam) even with the right code on the
# shortlist. Each product name is classified once and cached forever, and
# the code drives HS matching, Available Categories and SAM, so accuracy is
# worth the higher one-time cost.
MODEL = 'claude-sonnet-5'

SHORTLIST_SIZE = 10
BATCH_SIZE = 20  # products per Claude call — at 40, answers were occasionally lost mid-batch

# Words that appear throughout Comtrade's official descriptions as
# incidental color/grade/quality qualifiers on totally unrelated goods
# ("black, white or red currants", "red salmon", "extra virgin") — real
# signal when a product genuinely IS that color/grade, but never enough on
# their own to justify a match, and never allowed to outweigh a real
# subject-noun mismatch.
WEAK_WORDS = {
    'white', 'red', 'black', 'green', 'yellow', 'brown', 'pink', 'blue', 'purple', 'golden', 'gold',
    'large', 'small', 'medium', 'extra', 'jumbo', 'grade', 'fine', 'coarse', 'whole', 'fresh', 'new',
}
STOPWORDS = {
    'the', 'and', 'or', 'of', 'other', 'than', 'not', 'fit', 'for', 'human', 'consumption', 'otherwise',
    'including', 'local', 'imported', 'domestic', 'various', 'mixed', 'cut', 'piece', 'pieces', 'pack', 'box',
    'bag', 'bunch', 'unit', 'units', 'general', 'type', 'kind', 'kinds', 'per', 'with', 'without', 'used',
}
# A processed/preserved state on ONE side (product says fresh, reference
# means canned, or vice versa) should count against a match, not for it —
# this app is wholesale/retail spot-market prices, so "fresh" is the
# default assumption unless the product name says otherwise.
PROCESSED_STATE_WORDS = {'prepared', 'preserved', 'powder', 'flour', 'juice', 'smoked', 'salted', 'brine', 'canned', 'dried', 'starch'}

# The handful of everyday commodity words whose official HS term is a
# completely different word, not a spelling/grammar variant stemming can
# close — confirmed while building this: "beef" shares zero words with
# Comtrade's own "bovine animals" text, so a product literally named "Beef
# Liver" scored equally against POULTRY and FISH liver codes (which happen
# to share the bare word "liver") as against any actual bovine one, because
# no bovine-specific heading ever matched on "beef" at all; "Beef Mince",
# "Beef Ribs" and "Beef Loin" fared even worse, since without "bovine" they
# got no chapter-02 candidates whatsoever. Expanded, not replaced, so both
# the colloquial and official word are searchable either way.
SYNONYMS = {
    'beef': ['bovine'],
    'pork': ['swine', 'porcine'],
    'chicken': ['poultry', 'fowl'],
    'lamb': ['sheep', 'ovine'],
    'mutton': ['sheep', 'ovine'],
    'eggplant': ['aubergine'],
    'zucchini': ['squash', 'courgette'],
    'cilantro': ['coriander'],
    # Comtrade's fresh sweet/hot pepper entry (070960) never says "pepper",
    # only "capsicum" — without this a fresh pepper only ever matched the
    # dried-spice heading 0904 ("Pepper of the genus piper; ... capsicum").
    'pepper': ['capsicum'],
    'chili': ['capsicum'],
    'chilli': ['capsicum'],
    'cassava': ['manioc'],
    'yuca': ['manioc', 'cassava'],
}

_WORD_RE = re.compile(r'[a-z]+')

# From a product's category (e.g. "Pork", "Retail Meat — Chicken"), only the
# words naming the animal/commodity join its search terms — a cut name like
# "Primal Belly" or "Drumsticks" doesn't say which animal it is, and without
# that the only "belly" entry in the reference (cured belly, 021012) won
# outright. Generic category words ("Produce", "Retail") would only add noise.
CONTEXT_WORDS = {'beef', 'pork', 'chicken', 'poultry', 'lamb', 'mutton', 'goat', 'fish', 'seafood', 'egg', 'turkey', 'duck'}

# Chapter 24 (tobacco) is outside this app's food/agriculture domain; it only
# ever matched by accident ("Backs and Necks Stripped" -> stripped tobacco).
MAX_FOOD_CHAPTER = 23


def _context_terms(context: str) -> str:
    return ' '.join(word for word in _WORD_RE.findall((context or '').lower()) if _stem(word) in CONTEXT_WORDS)


def _stem(word: str) -> str:
    """Naive English pluralization stripping — not linguistically exact, but
    good enough to close the gap between how a product is named ("onion",
    "grapes") and however Comtrade's own text happens to phrase it, which is
    inconsistent even within itself (some entries use the plural, some the
    singular, for the same kind of thing). Without this, "onion" (singular)
    never matches Comtrade's "onions" (plural) at all — confirmed while
    building this: it produced zero candidates for "White Onion" — and worse,
    a product can lose to an unrelated processed/derivative entry that
    happens to share its exact grammatical form (a fresh "Apples; fresh"
    entry lost to "Apple juice" purely because "apple" is singular there and
    plural on the fresh-fruit entry)."""
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith(('oes', 'ches', 'shes', 'xes')) and len(word) > 4:
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss') and len(word) > 3:
        return word[:-1]
    return word


def _tokenize(text: str) -> list[str]:
    tokens = [_stem(w) for w in _WORD_RE.findall((text or '').lower()) if len(w) > 2 and w not in STOPWORDS]
    for token in list(tokens):
        tokens.extend(SYNONYMS.get(token, []))
    return tokens


def _subject_tokens(description: str) -> set[str]:
    """The words right after the description's first semicolon (its actual
    subject — "Vegetables, alliaceous; ONIONS AND SHALLOTS, fresh or
    chilled" — as opposed to the broad group before it, or the qualifiers
    after the next comma)."""
    after_semicolon = description.split(';', 1)[1] if ';' in description else description
    subject = after_semicolon.split(',', 1)[0]
    return set(_tokenize(subject))


def _score(product_tokens: set[str], product_has_processed_state: bool, entry: dict) -> float:
    ref_tokens = set(_tokenize(entry['description']))
    subject = _subject_tokens(entry['description'])
    strong_shared = (ref_tokens - WEAK_WORDS) & (product_tokens - WEAK_WORDS)
    if not strong_shared:
        return 0.0
    score = len(strong_shared) * 2
    score += len(subject & product_tokens) * 3  # a subject-word hit is worth much more than an incidental one
    weak_shared = (ref_tokens & WEAK_WORDS) & (product_tokens & WEAK_WORDS)
    score += len(weak_shared) * 0.5  # color/grade agreement is a fine tiebreaker, never the deciding signal
    ref_has_processed_state = bool(PROCESSED_STATE_WORDS & ref_tokens)
    if product_has_processed_state == ref_has_processed_state:
        score += 1
    if entry['level'] == 6:
        score += 0.25  # prefer the more specific code on an otherwise-tied score
    return score


def shortlist_candidates(name: str, limit: int = SHORTLIST_SIZE, context: str = '') -> list[dict]:
    """Best-guess HS codes for a product name, best first — cheap and
    deterministic, meant to be narrowed further (by a human or by Claude),
    not trusted as a final answer on its own. Scoped to the food/agriculture
    chapters (01-24), this app's whole domain. Empty means no keyword
    overlap at all — not "not a food item", since Comtrade's own English is
    often a different word for the same thing than ours (confirmed while
    building this: keyword scoring finds nothing at all for "Eggplant"
    (Comtrade says "aubergine"), "Chicken" ("fowls"), "Zucchini" (grouped
    under "pumpkins, squash and gourds (Cucurbita spp.)" with no literal
    "zucchini"/"courgette" anywhere), or "Soursop" (not named at all — just
    "other fruit, n.e.c."). See _FOOD_HEADINGS below for what covers those."""
    product_tokens = set(_tokenize(f'{name} {_context_terms(context)}'))
    if not product_tokens:
        return []
    has_processed_state = bool(PROCESSED_STATE_WORDS & product_tokens)
    scored = []
    for entry in classification.list_searchable_hs_codes():
        if int(entry['chapter']) > MAX_FOOD_CHAPTER:
            continue
        score = _score(product_tokens, has_processed_state, entry)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    pool = [entry for _, entry in scored[: limit * 2]]
    # A 4-digit heading is dropped whenever any of its own 6-digit
    # subheadings made the list too, so the more specific code is the only
    # way to pick that heading (the broad "0207" was being chosen over
    # "020713 ... cuts and offal, fresh or chilled" for chicken cuts).
    six_digit = [entry['hs_code'] for entry in pool if len(entry['hs_code']) == 6]
    pool = [entry for entry in pool if len(entry['hs_code']) != 4 or not any(code.startswith(entry['hs_code']) for code in six_digit)]
    return pool[:limit]


_food_headings_cache: list[dict] | None = None


def _food_headings() -> list[dict]:
    """Every 4-digit heading across the food/agriculture chapters (01-24) —
    a couple hundred entries, small enough to hand Claude directly as a
    candidate pool when keyword matching finds nothing at all. Keyword
    overlap can't bridge a genuine vocabulary gap (our "eggplant" vs
    Comtrade's "aubergine"); Claude's own knowledge of the same commodity
    under a different name can, as long as it's still limited to picking
    from a real list rather than free-form guessing."""
    global _food_headings_cache
    if _food_headings_cache is None:
        _food_headings_cache = [
            entry for entry in classification.list_searchable_hs_codes() if entry['level'] == 4 and int(entry['chapter']) <= MAX_FOOD_CHAPTER
        ]
    return _food_headings_cache


def _api_key() -> str | None:
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _ask_claude(items: list[tuple[str, str, list[dict]]]) -> dict[str, str | None]:
    """items: [(product_name, category, shortlist)]. Returns {product_name:
    hs_code or None} — Claude picks only from each product's own shortlist
    (never invents a code) or says none of them fit. Raises on any API or
    parsing failure: a None here is cached permanently as "unclassifiable",
    so it must only ever mean Claude's real answer, never an outage."""
    api_key = _api_key()
    if not api_key:
        raise RuntimeError('No Claude API key configured (CLAUDE_API_KEY).')

    blocks = []
    for index, (name, context, candidates) in enumerate(items, start=1):
        options = '\n'.join(f'   - {c["hs_code"]}: {c["description"]}' for c in candidates)
        label = f'"{name}" (category: {context})' if context else f'"{name}"'
        blocks.append(f'{index}. Product: {label}\n   Candidate HS codes:\n{options}')
    prompt = f"""We sell wholesale food/agricultural products. For each product below, pick the ONE HS \
(Harmonized System) customs code from its own candidate list that correctly identifies it — these are official \
UN Comtrade classification codes, used for e.g. onions -> 070310. Pick fresh/chilled over frozen and over \
processed/prepared unless the product name or category itself says otherwise (dried, frozen, canned, etc.) — never pick a salted, smoked, \
cured, dried, cooked or otherwise prepared code for a product whose name doesn't say so. A product's category, \
when given, tells you which animal or commodity it is (a "Primal Belly" in category Pork is fresh pork belly), \
and the code must be for that animal or commodity. The country it's sold in tells you what a regional name means \
(in Jamaica, "coco" is cocoyam/dasheen, a root crop — not coconut). Classify what the product IS, never an \
ingredient or flavour named in it: a salami with black pepper is a sausage (1601), a bean-and-cheese burrito is a \
prepared food, not beans. A compound name is one product: "banana passionfruit" is a passion fruit, not a banana; \
"tree tomato" is tamarillo, not a tomato. If the candidates only fit an ingredient or a word in the name, not the \
product itself, use null. Prefer the most specific 6-digit code that fits. If truly none \
of a product's candidates fit it, use null for that product — never invent a code that isn't in its list.

Return ONLY a JSON array (no prose, no code fence), one entry per product, in the same order: \
[{{"index": <the product's number above>, "hs_code": "<code from its list>" or null}}, ...]

Products:
{chr(10).join(blocks)}"""

    response = httpx.post(
        ANTHROPIC_API_URL,
        headers={'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'},
        json={'model': MODEL, 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': prompt}]},
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f'Claude API error {response.status_code}: {response.text[:300]}')

    text = ''.join(b.get('text', '') for b in response.json().get('content', []) if b.get('type') == 'text')
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise RuntimeError("Claude's classification reply contained no JSON array.")
    rows = json.loads(match.group(0))

    # Matched by position, not by the name Claude echoes back — a name with
    # punctuation ("Cassava / Yuca") echoed even slightly differently used
    # to silently lose its answer.
    results = {name: None for name, _, _ in items}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('index'), int):
            continue
        position = row['index'] - 1
        if not 0 <= position < len(items):
            continue
        name, _context, candidates = items[position]
        code = row.get('hs_code')
        if code in {c['hs_code'] for c in candidates}:
            results[name] = code
    return results


def _description_for(hs_code: str) -> str:
    return classification.hs_name(hs_code)


def _classify_one(name: str, context: str = '') -> tuple[dict | None, tuple[str, list[dict]] | None]:
    """Either a confident result straight away, or (None, (name, candidates))
    to hand to Claude — never both. `context` is the product's category."""
    shortlist = shortlist_candidates(name, context=context)
    if not shortlist:
        # No keyword overlap at all doesn't mean "not classifiable" — it
        # often means Comtrade just uses a different English word for the
        # same thing. Hand Claude every food-chapter heading instead of
        # giving up, so its own knowledge (aubergine=eggplant, fowls=
        # chicken, ...) has a real, grounded list to place the product in.
        broad = _food_headings()
        return (None, (name, broad)) if broad else (None, None)
    tokens = set(_tokenize(f'{name} {_context_terms(context)}'))
    has_processed_state = bool(PROCESSED_STATE_WORDS & tokens)
    top = shortlist[0]
    top_score = _score(tokens, has_processed_state, top)
    runner_up_score = _score(tokens, has_processed_state, shortlist[1]) if len(shortlist) > 1 else 0
    # An unambiguous top hit (clearly ahead of the runner-up, and it
    # actually shares the reference's own subject word — not just an
    # incidental one) is trusted without spending a Claude call on it.
    subject_hit = bool(_subject_tokens(top['description']) & tokens)
    if subject_hit and top_score >= runner_up_score * 1.6:
        return {'hs_code': top['hs_code'], 'description': top['description']}, None
    return None, (name, shortlist)


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
    request-scoped one closes the moment the triggering request returns,
    same reasoning as weight_research.py's _run_weight_research. `items` is
    [{key, name}]; a key already cached is skipped (checked again here,
    not just by the caller, in case two requests raced to start a job for
    overlapping items)."""
    db = SessionLocal()
    try:
        existing_keys = {
            key for (key,) in db.query(models.ProductHsCode.product_key).filter(models.ProductHsCode.product_key.in_([i['key'] for i in items]))
        }
        to_classify = [item for item in items if item['key'] not in existing_keys]
        if not to_classify:
            return

        # Stage 1: cheap deterministic shortlist per product — an
        # unambiguous hit needs no Claude call at all.
        to_ask_claude: list[tuple[str, str, str, list[dict]]] = []  # (key, name, context, shortlist)
        results: dict[str, dict | None] = {}
        for item in to_classify:
            context = item.get('context') or ''
            confident, pending = _classify_one(item['name'], context)
            if pending:
                to_ask_claude.append((item['key'], pending[0], context, pending[1]))
            else:
                results[item['key']] = confident

        # Stage 2: batch whatever's still ambiguous to Claude, grounded to
        # each product's own shortlist.
        # A batch whose Claude call fails is left uncached, so it's retried on
        # the next portfolio load instead of being stored as "unclassifiable".
        failure = None
        broad = _food_headings()
        for pass_items in (to_ask_claude, None):
            if pass_items is None:
                # Second pass: a product whose keyword shortlist had nothing
                # that fits ("Basa Fish" — Comtrade only says Pangasius) is
                # asked once more against every food-chapter heading, so it
                # can still land on the right heading instead of nothing.
                pass_items = [
                    (key, name, context, broad)
                    for key, name, context, shortlist in to_ask_claude
                    if key in results and results[key] is None and shortlist is not broad
                ]
            for start in range(0, len(pass_items), BATCH_SIZE):
                batch = pass_items[start : start + BATCH_SIZE]
                try:
                    answers = _ask_claude([(name, context, shortlist) for _, name, context, shortlist in batch])
                except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                    failure = exc
                    for key, *_ in batch:
                        results.pop(key, None)
                    continue
                for key, name, _context, _shortlist in batch:
                    code = answers.get(name)
                    results[key] = {'hs_code': code, 'description': _description_for(code)} if code else None

        # A real null answer (nothing in the food/agriculture chapters fits)
        # is cached too, so it isn't retried forever.
        for key, result in results.items():
            db.add(models.ProductHsCode(product_key=key, hs_code=result['hs_code'] if result else None, description=result['description'] if result else None))
        db.commit()
        if failure:
            raise RuntimeError(f'Some products could not be classified and will be retried: {failure}')
    finally:
        db.close()
