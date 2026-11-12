"""Which downloaded products belong in the main catalog and which go to the secondary (discarded) list.

The supermarket-style catalogs are scraped by category and carry products nobody here will trade (cookies, dough, drinks, sauces ...), some of them filed under a produce
category. This module reads each product's name, store category and HS code (all already stored with it) and gives it a `scope` block:

    {status: 'main' | 'secondary', reason, rule, confidence: 'high' | 'medium' | 'low' | 'user'}

IN: fresh produce, fresh / frozen meat, poultry and fish, processed meat that needs refrigeration or the cold chain, cheese, eggs. OUT: every other dairy, canned or shelf-stable
meat and fish (they travel by sea), frozen / canned / dried produce, nuts, rice and grains, flour, bakery, sweets, drinks, sauces, spices, non-food. The rules are data
(data/scope_rules.json) so they can be edited without touching code. A product is never dropped: the secondary ones stay stored and can be listed and moved back (scope_store.py).
A choice a person made always wins over the rules. Only the supermarket-style catalogs are classified (`applies_to`); the wholesale sources are always main.
Pure functions of plain dicts: no database, no web, no model."""

import json
import re
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / 'data' / 'scope_rules.json'
MAIN, SECONDARY = 'main', 'secondary'


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding='utf-8'))


@lru_cache(maxsize=256)
def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


def applies_to(source_key: str, rules: dict | None = None) -> bool:
    return any(source_key.startswith(prefix) for prefix in (rules or load_rules())['applies_to'])


def is_main(product: dict) -> bool:
    """A product with no scope block (a wholesale source, or stored before this module) counts as main."""
    return (product.get('scope') or {}).get('status') != SECONDARY


def product_key(name: str) -> str:
    return ' '.join((name or '').lower().split())


def _verdict(status: str, reason: str, rule: str, confidence: str) -> dict:
    return {'status': status, 'reason': reason, 'rule': rule, 'confidence': confidence}


def classify(product: dict, rules: dict | None = None) -> dict:
    """The scope of one stored product. `product` has `name`, `category` and the `hs` block the HS step put on it. The HS code, when there is one, is trusted before the name
    words: a fresh-produce or meat code is not overruled by "honey" in "Honey Gold Potatoes", and "Four Cheese mashed potatoes" (chapter 11) is not cheese."""
    rules = rules or load_rules()
    name = (product.get('name') or '').strip()
    category = product.get('category') or ''
    hs6 = ((product.get('hs') or {}).get('hs6') or '')
    chapter, heading = hs6[:2], hs6[:4]
    keep_match = bool(_re(rules['keep_name']['match']).search(name))
    keep = keep_match and (chapter == '04' or (chapter == '' and not _re(rules['keep_name']['not']).search(name)))
    meat_rule = rules['cold_chain_meat']
    cold_meat = (chapter in meat_rule['chapters'] and bool(_re(meat_rule['match']).search(name)) and not _re(meat_rule['not']).search(name))
    category_out = bool(_re(rules['out_categories']).search(category))
    category_in = bool(_re(rules['in_categories']).search(category))

    # rules that apply before anything else can save a product: not food, canned / shelf-stable, plant-based "meat"
    early_ids = ('non_food', 'canned_shelf_stable', 'canned_weak', 'plant_based_meat')
    for rule in rules['out_rules']:
        if rule['id'] in early_ids and chapter not in rule.get('skip_when_chapter', ()) and _re(rule['name']).search(name):
            return _verdict(SECONDARY, rule['reason'], rule['id'], 'high')
    if _re(rules['canned_categories']).search(category):
        return _verdict(SECONDARY, 'Filed under a canned category: shelf-stable, moves by sea', 'canned_category', 'high')

    if chapter in ('02', '03'):
        return _verdict(MAIN, 'Meat or fish (fresh, frozen or cold chain)', f'hs_{chapter}', 'high')
    if cold_meat:
        if heading in rules['preserved_fish_headings'] and not category_in:
            return _verdict(SECONDARY, 'Preserved fish or shellfish (usually canned): not in the catalog', f'hs_{heading}', 'medium')
        return _verdict(MAIN, 'Processed meat or fish (cold chain)', 'cold_chain_meat', 'high' if chapter in ('16',) else 'medium')

    frozen = bool(_re(rules['frozen_produce']['name']).search(name)) or bool(_re(rules['frozen_produce']['category']).search(category))
    if frozen and (chapter in ('07', '08') or not chapter) and not keep:
        return _verdict(SECONDARY, rules['frozen_produce']['reason'], 'frozen_produce', 'high')

    if keep or heading in rules['in_headings']:
        return _verdict(MAIN, 'Cheese or eggs', 'keep_name' if keep else f'hs_{heading}', 'high')

    if hs6 and any(hs6.startswith(prefix) for prefix in rules['out_headings']['list']):
        return _verdict(SECONDARY, 'Dried, preserved or frozen: not in the catalog', f'hs_{hs6[:4]}', 'high')
    for rule in rules['out_rules']:
        if rule['id'] in early_ids or chapter in rule.get('skip_when_chapter', ()):
            continue
        if _re(rule['name']).search(name):
            return _verdict(SECONDARY, rule['reason'], rule['id'], 'high')

    herb = bool(_re(rules['fresh_herbs']).search(name))
    if chapter in rules['in_chapters'] or heading in rules['in_headings']:
        return _verdict(MAIN, 'Fresh produce, meat or fish', f'hs_{chapter}', 'medium' if category_out and not category_in else 'high')
    if chapter == '09' and herb and not category_out:
        return _verdict(MAIN, 'Fresh herb', 'fresh_herb', 'medium')
    if chapter == '04':
        return _verdict(SECONDARY, 'Dairy other than cheese and eggs: not in the catalog', 'hs_04', 'high')
    if chapter:
        return _verdict(SECONDARY, f'HS chapter {chapter} is outside the catalog scope', f'hs_{chapter}', 'high')

    # no HS code: the store's category and the name decide, with less confidence
    if herb and not category_out:
        return _verdict(MAIN, 'Fresh herb', 'fresh_herb', 'low')
    if category_in and not category_out:
        return _verdict(MAIN, 'Filed under a produce, meat or dairy category (no HS code)', 'category_in', 'low')
    if category_out:
        return _verdict(SECONDARY, 'Filed under a category outside the catalog scope (no HS code)', 'category_out', 'medium')
    # nothing says it is out: a product without a code is never dropped for that alone (it stays, flagged to check)
    return _verdict(MAIN, 'No HS code and no usable category: check it', 'unknown', 'low')


# The third portfolio of a country: main-catalog products with an open issue ("To check"). The three portfolios per country are Catalog (main, nothing open), To check (main, something
# open) and Discarded (secondary).
ISSUES = {
    'no_hs': 'No HS code',
    'old_hs': 'Old HS code (not in HS 2022)',
    'no_price_per_kg': 'No price per kg yet',
    'unsure_scope': 'Not sure it belongs in the catalog',
}


def review_issues(product: dict) -> list[str]:
    """The issue codes (keys of ISSUES) a stored product still has; [] for a ready product and for a discarded one (nothing to fix there)."""
    block = product.get('scope') or {}
    if block.get('status') == SECONDARY:
        return []
    issues = []
    hs = product.get('hs') or {}
    if not hs.get('hs6'):
        issues.append('no_hs')
    elif hs.get('obsolete'):
        issues.append('old_hs')
    if (product.get('norm') or {}).get('method') in ('needs_research', 'unconvertible'):
        issues.append('no_price_per_kg')
    if block.get('confidence') == 'low':
        issues.append('unsure_scope')
    return issues


def with_override(scope: dict, override: str | None) -> dict:
    """A person's choice ('main' | 'secondary') replaces the rules' verdict."""
    if override not in (MAIN, SECONDARY) or override == scope['status'] and scope.get('rule') == 'override':
        return scope
    return {'status': override, 'reason': 'Moved by you', 'rule': 'override', 'confidence': 'user', 'rules_said': scope['status']}
