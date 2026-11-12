"""HS codes inside the normalization module.

Every catalog product gets an `hs` block next to its `norm` block (catalog.py `annotate_rows`). The code a product shows is always
`<ISO2 of the country it is sold in><6-digit HS code>` (e.g. `JM070200`); there are NO placeholder codes: a product without a code has `hs.code = None` and the label
`no_code`, and a code that is only a 4-digit heading padded with '00' (e.g. 0201 -> 020100, because 0201 has no single subheading) is labelled `heading_only`.

Where a product's code comes from, in the order they are looked up when a catalog is stored (no web or model call there, ever):
  1. product_hs_assignments  (country + English name) — saved by a person (status confirmed / corrected) or accepted from a suggestion (status suggested)
  2. product_hs_codes        — the older name-only cache of the AI classifier; read as 'suggested' for every country that has no row of its own

Suggesting a code is a separate, explicit step (`suggest`), free sources first, and NEVER saves anything:
  rule   data/hs_item_rules.json — curated, exact (empty until a person adds rules)
  peer   the same product already coded in another country
  local  a local Ollama model restricted to the headings / subheadings of the reference (free, less accurate)
  ai     Claude via comtrade/product_classification.py (paid, only when asked)
Every code is checked against Comtrade's HS reference (comtrade/classification.py): it must exist, a 4-digit heading is padded, the chapter is compared with the
product's category, and the same product coded differently in another country is flagged."""

import json
import re
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

from ..comtrade import classification

RULES_FILE = Path(__file__).resolve().parent / 'data' / 'hs_item_rules.json'
FOOD_LAST_CHAPTER = 23
EDIBLE_OUTSIDE = ('2501',)  # salt

# Chapters a product category normally falls in. A category not listed is not checked. Only a WARNING when it disagrees: a person may know better.
CATEGORY_CHAPTERS: dict[str, set[str]] = {
    'beef': {'02', '16'}, 'pork': {'02', '16'}, 'poultry': {'02', '16'}, 'eggs': {'04'},
    'grains (export)': {'10', '11', '12'},
    'produce (fl shipping point)': {'07', '08', '09', '12', '20'}, 'produce (ca shipping point)': {'07', '08', '09', '12', '20'},
    'retail produce': {'07', '08', '09', '20'},
    # Colombia's catalog categories
    'pollo': {'02', '16'}, 'carnicos': {'02', '16'}, 'huevos': {'04'}, 'pescados_mariscos': {'03', '16'}, 'hortalizas': {'07', '12', '20'},
    'tuberculos': {'07', '11'}, 'platanos': {'07', '08'}, 'frutas': {'08', '20', '12'},
}


class HsError(ValueError):
    """A reason an HS code (or a request about one) is refused; the text is shown to the person."""


def hs_key(name: str) -> str:
    """The key a product is stored under: its (English) name, trimmed and lowercased — the same key the older name-only cache uses."""
    return (name or '').strip().lower()


@dataclass
class Code:
    hs6: str
    level: int  # 6: a real subheading; 4: a heading padded with '00'
    description: str


def parse_code(raw) -> Code:
    """'0702', '070200', '0702.00', 'JM070200' ... -> Code. A 4-digit heading is padded with '00': when that padded code is itself a subheading of the reference
    (0702.00) it is a real 6-digit code, otherwise (0201 -> 020100) it stays level 4. Raises HsError with a reason a person can act on."""
    digits = re.sub(r'\D', '', str(raw or ''))
    reference = classification.reference_codes()
    if not reference:
        raise HsError('The HS reference could not be loaded, so a code cannot be checked right now.')
    current = classification.current_codes()  # HS 2022, the nomenclature in force: a code of an older revision is not a code any more
    old = ' was a code of an older HS revision and no longer exists in HS 2022 (the current nomenclature): choose its current code.'
    if len(digits) == 6:
        if digits in reference:
            if current and digits not in current:
                if digits.endswith('00') and digits[:4] in current:  # 100300 (barley): the heading still exists, it only gained subheadings (100310, 100390)
                    return Code(digits, 4, reference[digits[:4]] if digits[:4] in reference else current[digits[:4]])
                raise HsError(f'{digits}{old}')
            return Code(digits, 6, reference[digits])
        if digits.endswith('00') and digits[:4] in reference:  # the padded form of a heading without subheadings, e.g. 020100
            if current and digits[:4] not in current:
                raise HsError(f'Heading {digits[:4]}{old}')
            return Code(digits, 4, reference[digits[:4]])
        raise HsError(f'{digits} is not an HS subheading in the HS reference.')
    if len(digits) == 4:
        if digits not in reference:
            raise HsError(f'{digits} is not an HS heading in the HS reference.')
        if current and digits not in current:
            raise HsError(f'Heading {digits}{old}')
        padded = digits + '00'
        return Code(padded, 6, reference[padded]) if padded in reference else Code(padded, 4, reference[digits])
    raise HsError('Give a 4-digit heading or a 6-digit subheading (a 2-digit chapter is too coarse to trade).')


def label_for(code: str | None, level: int | None, obsolete: bool = False) -> str:
    if not code:
        return 'no_code'
    if obsolete:
        return 'obsolete'  # a code of an older HS revision: it no longer exists in HS 2022 and must be replaced
    return 'heading_only' if level == 4 else 'ok'


def is_obsolete(hs6: str | None, level: int | None) -> bool:
    """True when the code is not in HS 2022 (a padded heading is judged by its heading)."""
    current = classification.current_codes()
    if not hs6 or not current:
        return False
    return (hs6[:4] not in current) if level == 4 else (hs6 not in current)


# ---------------------------------------------------------------- lookup

class HsIndex:
    """Everything the lookup needs, read once per annotate/queue run: the per-country assignments, the older name-only codes and the ISO2 of each country."""

    def __init__(self, assignments: dict, legacy: dict[str, str], iso2: dict[str, str]):
        self.assignments = assignments  # (country lower, key) -> dict(hs_code, hs_level, status, method, confidence, note)
        self.legacy = legacy  # key -> hs_code (4 or 6 digits)
        self.iso2 = iso2  # country lower -> ISO2

    def block(self, country: str | None, name: str) -> dict:
        """The `hs` block of one product: {code, hs6, level, label, status, method, description, iso2, source, ai_suggested}."""
        key = hs_key(name)
        iso = self.iso2.get((country or '').strip().lower())
        row = self.assignments.get(((country or '').strip().lower(), key))
        source = 'assignment'
        if row:
            hs6, level, status, method, description = row['hs_code'], row['hs_level'], row['status'], row['method'], ''
            try:
                description = parse_code(hs6).description
            except HsError:
                pass
        elif key in self.legacy:
            source, status, method = 'legacy', 'suggested', 'ai'
            try:
                parsed = parse_code(self.legacy[key])
                hs6, level, description = parsed.hs6, parsed.level, parsed.description
            except HsError:
                digits = re.sub(r'\D', '', self.legacy[key])
                hs6, level, description = (digits + '00')[:6], 4 if len(digits) == 4 else 6, ''
        else:
            return {'code': None, 'hs6': None, 'level': None, 'label': 'no_code', 'status': None, 'method': None, 'description': '', 'iso2': iso, 'source': None, 'ai_suggested': False, 'obsolete': False}
        obsolete = is_obsolete(hs6, level)
        return {'code': f'{iso}{hs6}' if iso else None, 'hs6': hs6, 'level': level, 'label': label_for(hs6, level, obsolete), 'status': status, 'method': method,
                'description': description, 'iso2': iso, 'source': source, 'ai_suggested': status == 'suggested', 'obsolete': obsolete}


def build_index(db) -> HsIndex:
    from .. import models

    assignments = {
        ((row.country or '').strip().lower(), row.product_key): {'hs_code': row.hs_code, 'hs_level': row.hs_level or 6, 'status': row.status, 'method': row.method,
                                                                 'confidence': row.confidence, 'note': row.note}
        for row in db.query(models.ProductHsAssignment).all()
    }
    legacy = {row.product_key: row.hs_code for row in db.query(models.ProductHsCode).all() if row.hs_code}
    iso2 = {(row.name or '').strip().lower(): row.country_code for row in db.query(models.CountryReferenceCatalog).all() if row.country_code}
    return HsIndex(assignments, legacy, iso2)


# ---------------------------------------------------------------- validation

def check(country: str, name: str, category: str | None, raw_code, index: HsIndex | None = None) -> dict:
    """{status: ok | warning | error, messages, hs6, level, description}. An error is refused when saving; a warning is shown and may be accepted."""
    try:
        code = parse_code(raw_code)
    except HsError as error:
        return {'status': 'error', 'messages': [str(error)], 'hs6': None, 'level': None, 'description': ''}
    messages, status = [], 'ok'

    def warn(text: str) -> None:
        nonlocal status
        messages.append(text)
        status = 'warning'

    chapter = code.hs6[:2]
    if int(chapter) > FOOD_LAST_CHAPTER and code.hs6[:4] not in EDIBLE_OUTSIDE:
        warn(f'Chapter {chapter} is outside food and agriculture (01-23); check this is what is sold.')
    if code.level == 4:
        warn(f'Heading {code.hs6[:4]} has no subheading chosen, so the code is stored padded as {code.hs6} and labelled "heading only".')
    expected = CATEGORY_CHAPTERS.get((category or '').strip().lower())
    if expected and chapter not in expected:
        warn(f'The category "{category}" normally falls in chapter {" / ".join(sorted(expected))}, but this code is in chapter {chapter}.')
    if index is not None:
        key = hs_key(name)
        for (other_country, other_key), row in index.assignments.items():
            if other_key == key and other_country != (country or '').strip().lower() and row['hs_code'][:4] != code.hs6[:4]:
                warn(f'In {other_country.title()} the same product is coded {row["hs_code"]} (a different heading) — check both are right.')
                break
    return {'status': status, 'messages': messages, 'hs6': code.hs6, 'level': code.level, 'description': code.description}


# ---------------------------------------------------------------- suggestions (never saved here)

def load_rules() -> dict[str, str]:
    try:
        return {hs_key(key): value for key, value in json.loads(RULES_FILE.read_text(encoding='utf-8')).get('rules', {}).items()}
    except (OSError, ValueError):
        return {}


def suggest_from_rule(name: str) -> dict | None:
    code = load_rules().get(hs_key(name))
    return {'code': code, 'method': 'rule', 'confidence': 'high', 'note': 'A curated rule (data/hs_item_rules.json).'} if code else None


KEYWORD_RULES_FILE = RULES_FILE.parent / 'hs_keyword_rules.json'


@lru_cache(maxsize=1)
def _keyword_rules() -> dict:
    """data/hs_keyword_rules.json with every word list compiled once: a whole word, its plural optional (tomato -> tomatoes)."""
    def compile_words(words: list[str]):
        if not words:
            return None
        return re.compile(r'\b(?:' + '|'.join(re.escape(word) for word in sorted(words, key=len, reverse=True)) + r')(?:s|es)?\b', re.IGNORECASE)

    try:
        data = json.loads(KEYWORD_RULES_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'global_not': None, 'rules': []}
    return {'global_not': compile_words(data.get('global_not', [])),
            'rules': [{**rule, 'match': compile_words(rule['words']), 'exclude': compile_words(rule.get('not', []))} for rule in data.get('rules', [])]}


def match_keyword_rule(name: str, category: str | None = None) -> tuple[dict, bool] | None:
    """(rule, frozen) of the first keyword rule that names this product, or None: not a commodity the rules know, or a processed-food name. Shared by the HS suggestion and by the
    retail-unit table (which only answers for products the rules call PRODUCE: "Cream Cheese Strawberry" is a cheese)."""
    rules = _keyword_rules()
    # a bracketed label is a variety or a brand note ("Sweet Potato (Local Chicken foot)", "Arracacha (Peruvian Carrot)"): it must not decide the commodity
    text = re.sub(r'[^a-z0-9 ]+', ' ', re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', (name or '').lower()))
    if not text.strip() or (rules['global_not'] and rules['global_not'].search(text)):
        return None
    frozen = bool(re.search(r'\bfrozen\b', text) or re.search(r'\bfrozen\b', (category or '').lower()))
    for rule in rules['rules']:
        found = rule['match'].search(text)
        if found and not (rule['exclude'] and rule['exclude'].search(text)):
            return {**rule, 'matched': found.group(0), 'text': text}, frozen
    return None


def suggest_from_keywords(name: str, category: str | None = None) -> dict | None:
    """The backup before any AI: the first keyword rule (data/hs_keyword_rules.json) whose word is in the English name. Fresh / chilled code by default, the frozen code when the name
    or the store category says frozen. Nothing guessed: a name no rule knows, or one with a processed-food word (sauce, juice, dried ...), gets no suggestion."""
    matched = match_keyword_rule(name, category)
    if matched is None:
        return None
    rule, frozen = matched
    code = rule.get('frozen_code') if frozen else rule['code']
    if 'fillet_code' in rule and re.search(r'\bfillets?\b', rule['text']):  # fish fillets are another heading (0304): only the species that have a fillet code are suggested
        code = rule.get('fillet_frozen_code') if frozen else rule.get('fillet_code')
    if not code:
        return None
    note = f"Keyword rule \u201c{rule['matched']}\u201d: {rule['note']}" + (' (frozen)' if frozen and rule.get('frozen_code') != rule['code'] else '') + '.'
    return {'code': code, 'method': 'rule', 'confidence': rule.get('confidence', 'medium'), 'note': note}


SPECIAL_PURPOSE = {'seed', 'seeds', 'breeding', 'sowing', 'planting', 'live', 'purebred'}  # a child of a heading made for another use than eating / trading the commodity itself


def suggest_from_schedule_b(name: str, heading: str | None = None) -> dict | None:
    """The last free step: the US Schedule B text (the same codes as HS 2022 with their descriptions). Answers only when every word of the name is a word the Schedule B uses and exactly one
    six-digit code holds all of them ("Salt" -> 250100, "Lentils" -> 071340); two codes or more, or a word it does not know (a brand, a regional name), and it says nothing.
    `heading` is the 4-digit heading the product already has (an old or heading-only code): the search then stays inside it, and of the codes left the special-purpose ones (seed, breeding
    stock ...) are dropped unless the name asks for them, so "Barley" under 1003 is 100390 (other than seed), not 100310 (seed)."""
    from . import schedule_b

    words = set(schedule_b.tokens(re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', name or '')))
    if not words or not words <= set(schedule_b._index()['idf']):
        return None
    heading = heading if heading and len(heading) == 4 and heading in classification.current_codes() else ''
    found = [row for row in schedule_b.search(name, 40, within=heading) if row['score'] >= 0.999]
    if heading and len(found) > 1:
        found = [row for row in found if not (SPECIAL_PURPOSE & set(schedule_b.tokens(row['text'])) - words)]  # the Schedule B path ("Barley > Seed"; "Barley > Other"), not the HS wording ("other than seed")
    if len(found) != 1:
        return None
    where = f' inside heading {heading}' if heading else ''
    return {'code': found[0]['code'], 'method': 'schedule_b', 'confidence': 'low', 'note': f"The only code{where} whose US Schedule B text has every word of the name: {found[0]['text'][:120]}."}


def suggest_from_peers(index: HsIndex, country: str, name: str) -> dict | None:
    """The code another country already uses for the same name. A code a person confirmed outweighs an AI one; when they disagree the commonest wins and the
    note says so, so the person decides."""
    key, own = hs_key(name), (country or '').strip().lower()
    found = [(other, row) for (other, other_key), row in index.assignments.items() if other_key == key and other != own]
    if not found:
        return None
    people = [item for item in found if item[1]['status'] in ('confirmed', 'corrected')] or found
    counts = Counter(row['hs_code'] for _other, row in people)
    best, _n = counts.most_common(1)[0]
    where = ', '.join(sorted({other.title() for other, row in found if row['hs_code'] == best}))
    note = f'The same product is coded {best} in {where}.'
    if len(counts) > 1:
        note += ' Other countries use ' + ', '.join(sorted(code for code in counts if code != best)) + ' — check which is right.'
    return {'code': best, 'method': 'peer', 'confidence': 'medium', 'note': note, 'by_person': any(row['status'] in ('confirmed', 'corrected') and row['hs_code'] == best for _other, row in found)}


def _clean_description(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^[-\s:]+', '', text or '')).strip()[:90]


def suggest_with_claude(items: list[dict]) -> list[dict | None]:
    """Claude (paid). Raises when the call fails — the caller reports the real reason."""
    from ..comtrade import product_classification as claude_classifier

    codes = claude_classifier.classify_products([(item['name'], f"{item.get('category') or 'Uncategorized'}; sold in {item.get('country') or 'unknown'}") for item in items])
    return [{'code': code, 'method': 'ai', 'confidence': 'medium', 'note': 'Suggested by Claude from the HS reference; check it.'} if code else None for code in codes]


def suggest(db, items: list[dict], *, allow_peer: bool = True, allow_ai: bool = False) -> dict:
    """items: [{country, name, category?}] -> {results: [{country, name, category, suggestion, validation, tried}], errors: [..]}. Nothing is saved."""
    index = build_index(db)
    results = [{'country': item['country'], 'name': item['name'], 'category': item.get('category'), 'suggestion': None, 'tried': []} for item in items]
    errors: list[str] = []

    def take(position: int, found: dict | None, tried: str) -> None:
        results[position]['tried'].append(tried)
        if found and not results[position]['suggestion']:
            results[position]['suggestion'] = found

    for position, item in enumerate(items):
        # order of trust: an exact curated rule, a code a PERSON confirmed for the same product in another country, the keyword rules, then a code another country only had suggested
        take(position, suggest_from_rule(item['name']), 'rule')
        peer = suggest_from_peers(index, item['country'], item['name']) if allow_peer else None
        if peer and peer.get('by_person'):
            take(position, peer, 'peer')
        take(position, suggest_from_keywords(item['name'], item.get('category')), 'keyword')
        if peer and not peer.get('by_person'):
            take(position, peer, 'peer')
        if not results[position]['suggestion']:
            stored = index.assignments.get(((item['country'] or '').strip().lower(), hs_key(item['name'])), {}).get('hs_code') or index.legacy.get(hs_key(item['name'])) or ''
            take(position, suggest_from_schedule_b(item['name'], re.sub(r'\D', '', stored)[:4]), 'schedule_b')

    if allow_ai:
        pending = [i for i, row in enumerate(results) if not row['suggestion']]
        if pending:
            try:
                answers = suggest_with_claude([{**items[i]} for i in pending])
            except Exception as error:  # noqa: BLE001 — shown to the person: credits, no key ...
                errors.append(f'ai: {error}')
            else:
                for i, answer in zip(pending, answers):
                    take(i, answer, 'ai')

    for row in results:
        if row['suggestion']:
            verdict = check(row['country'], row['name'], row['category'], row['suggestion']['code'], index)
            row['validation'] = verdict
            if verdict['status'] == 'error':  # a suggestion the reference does not know is dropped, not shown as usable
                row['suggestion'] = None
        else:
            row['validation'] = None
    return {'results': results, 'errors': errors}
