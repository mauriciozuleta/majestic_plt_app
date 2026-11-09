"""Item weights from published data, no AI and no network: USDA's Standard Reference table (data/usda_sr28_produce.json, built by build_usda_reference.py) read
through a hand-curated rule list (data/usda_item_rules.json) that says which USDA food and which household measure ("1 fruit", "1 head, medium", "1 bunch")
stands for a product name. A product with no rule is not answered from here — there is no fuzzy matching, because a wrong match (a banana pepper for a bell pepper)
is worse than no answer. What this module cannot answer (bunches of herbs, lulo, curuba, tamarillo ...) falls through to web research or a hand-typed weight.

USDA household weights describe the EDIBLE part, so for the rules marked `edible` the weight of the item as it is bought is grams / (1 - refuse%): 1 pineapple = 905 g
edible, refuse 49% (skin, core, crown) -> about 1,775 g. A head or bunch (`as_sold`) is taken as it is. The edible weight is kept as the low end of the range."""

import json
import re
from functools import lru_cache
from pathlib import Path

import unicodedata

from .store import ItemWeight

DATA = Path(__file__).resolve().parent / 'data'
SOURCE_URL = 'https://www.ars.usda.gov/northeast-area/beltsville-md-bhnrc/beltsville-human-nutrition-research-center/methods-and-application-of-food-composition-laboratory/mafcl-site-pages/sr28-sr27/'


@lru_cache(maxsize=1)
def _foods() -> dict:
    return json.loads((DATA / 'usda_sr28_produce.json').read_text(encoding='utf-8'))['foods']


@lru_cache(maxsize=1)
def _rules() -> list[dict]:
    rules = json.loads((DATA / 'usda_item_rules.json').read_text(encoding='utf-8'))['rules']
    return [{**rule, '_match': re.compile(rule['match'], re.IGNORECASE), '_exclude': re.compile(rule['exclude'], re.IGNORECASE) if rule.get('exclude') else None} for rule in rules]


def _key(name: str) -> str:
    """Lowercase, no accents, punctuation to spaces — but the words in parentheses are KEPT ("Peppers (Bell Type)" is a bell pepper), unlike the cache key."""
    text = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9, ]+', ' ', text)).strip()


def lookup(name: str, count_unit: str = 'each') -> ItemWeight | None:
    """The weight of ONE item of `name` from USDA's table, or None when no rule covers the product (or its unit)."""
    key = _key(name)
    for rule in _rules():
        if not rule['_match'].search(key) or (rule['_exclude'] and rule['_exclude'].search(key)):
            continue
        if rule['unit'] != count_unit and not (count_unit == 'head' and rule['unit'] == 'each'):
            continue
        food = _foods().get(rule['ndb'])
        if food is None:
            continue
        portion = next((p for p in food['portions'] if re.search(rule['portion'], p[0], re.IGNORECASE) and p[1] > 0), None)
        if portion is None:
            continue
        description, grams, amount = portion
        grams = grams / (amount or 1)
        refuse = food['refuse_pct']
        if rule['basis'] == 'edible' and refuse < 90:
            as_bought = grams / (1 - refuse / 100)
            note = (f"USDA SR28 #{rule['ndb']} \"{food['desc']}\": {description} = {grams:.0f} g edible; refuse {refuse:.0f}%"
                    f"{' (' + food['refuse_desc'] + ')' if food['refuse_desc'] else ''} -> about {as_bought:.0f} g as bought.")
            return ItemWeight(name, count_unit, as_bought / 1000, grams / 1000, as_bought / 1000, confidence='medium', note=note, sources=[SOURCE_URL])
        note = f"USDA SR28 #{rule['ndb']} \"{food['desc']}\": {description} = {grams:.0f} g (taken as sold)."
        return ItemWeight(name, count_unit, grams / 1000, confidence='medium', note=note, sources=[SOURCE_URL])
    return None
