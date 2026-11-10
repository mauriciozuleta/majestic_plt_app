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
from dataclasses import dataclass
from pathlib import Path

from ..comtrade import classification

RULES_FILE = Path(__file__).resolve().parent / 'data' / 'hs_item_rules.json'
FOOD_LAST_CHAPTER = 23

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
        raise HsError('The HS reference (Comtrade) could not be loaded, so a code cannot be checked right now.')
    if len(digits) == 6:
        if digits in reference:
            return Code(digits, 6, reference[digits])
        if digits.endswith('00') and digits[:4] in reference:  # the padded form of a heading without subheadings, e.g. 020100
            return Code(digits, 4, reference[digits[:4]])
        raise HsError(f'{digits} is not an HS subheading in the Comtrade reference.')
    if len(digits) == 4:
        if digits not in reference:
            raise HsError(f'{digits} is not an HS heading in the Comtrade reference.')
        padded = digits + '00'
        return Code(padded, 6, reference[padded]) if padded in reference else Code(padded, 4, reference[digits])
    raise HsError('Give a 4-digit heading or a 6-digit subheading (a 2-digit chapter is too coarse to trade).')


def label_for(code: str | None, level: int | None) -> str:
    if not code:
        return 'no_code'
    return 'heading_only' if level == 4 else 'ok'


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
            return {'code': None, 'hs6': None, 'level': None, 'label': 'no_code', 'status': None, 'method': None, 'description': '', 'iso2': iso, 'source': None, 'ai_suggested': False}
        return {'code': f'{iso}{hs6}' if iso else None, 'hs6': hs6, 'level': level, 'label': label_for(hs6, level), 'status': status, 'method': method,
                'description': description, 'iso2': iso, 'source': source, 'ai_suggested': status == 'suggested'}


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
    if int(chapter) > FOOD_LAST_CHAPTER:
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
    return {'code': best, 'method': 'peer', 'confidence': 'medium', 'note': note}


def _clean_description(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^[-\s:]+', '', text or '')).strip()[:90]


def suggest_with_local_model(items: list[dict], model: str, cancel=None) -> list[dict | None]:
    """A local Ollama model picks the 4-digit heading from the food headings of the reference, then the 6-digit subheading from that heading's own lines (or keeps the
    heading). It can only answer with a code it was shown. One product per call; slow on a CPU and less accurate than Claude, but free."""
    import threading

    from ..comtrade import product_classification as claude_classifier
    from ..local_models import ollama_client

    cancel = cancel or threading.Event()
    headings = claude_classifier._headings()
    heading_codes = {entry['hs_code'] for entry in headings}
    heading_list = '\n'.join(f"{entry['hs_code']} {_clean_description(entry['description'])}" for entry in headings)
    system = ('You classify food and agricultural products into official HS codes. Classify what the product actually is (the commodity), fresh or chilled unless the name '
              'says otherwise. Answer with ONE code from the list and nothing else.')

    def ask(prompt: str) -> str:
        return ''.join(ollama_client.stream_chat(model, [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}], cancel,
                                                 {'temperature': 0, 'num_ctx': 8192, 'num_predict': 16})).strip()

    results: list[dict | None] = []
    for item in items:
        context = f"category: {item.get('category') or 'unknown'}; sold in {item.get('country') or 'unknown'}"
        reply = ask(f"HS headings:\n{heading_list}\n\nProduct: {item['name']} ({context})\nAnswer with the 4-digit heading code.")
        match = re.search(r'\b(\d{4})\b', reply)
        heading = match.group(1) if match and match.group(1) in heading_codes else None
        if not heading:
            results.append(None)
            continue
        options = claude_classifier._subheadings(heading)
        code = heading
        if options:
            lines = '\n'.join(f"{entry['hs_code']} {_clean_description(entry['description'])}" for entry in options)
            reply = ask(f"Subheadings of {heading}:\n{lines}\n\nProduct: {item['name']} ({context})\nAnswer with the 6-digit code, or {heading} if none fits.")
            match = re.search(r'\b(\d{6})\b', reply)
            if match and match.group(1) in {entry['hs_code'] for entry in options}:
                code = match.group(1)
        results.append({'code': code, 'method': 'local_model', 'confidence': 'low', 'note': f'Suggested by the local model {model}; check it.'})
    return results


def suggest_with_claude(items: list[dict]) -> list[dict | None]:
    """Claude (paid). Raises when the call fails — the caller reports the real reason."""
    from ..comtrade import product_classification as claude_classifier

    codes = claude_classifier.classify_products([(item['name'], f"{item.get('category') or 'Uncategorized'}; sold in {item.get('country') or 'unknown'}") for item in items])
    return [{'code': code, 'method': 'ai', 'confidence': 'medium', 'note': 'Suggested by Claude from the HS reference; check it.'} if code else None for code in codes]


def suggest(db, items: list[dict], *, allow_peer: bool = True, allow_local: bool = False, local_model: str | None = None, allow_ai: bool = False) -> dict:
    """items: [{country, name, category?}] -> {results: [{country, name, category, suggestion, validation, tried}], errors: [..]}. Nothing is saved."""
    index = build_index(db)
    results = [{'country': item['country'], 'name': item['name'], 'category': item.get('category'), 'suggestion': None, 'tried': []} for item in items]
    errors: list[str] = []

    def take(position: int, found: dict | None, tried: str) -> None:
        results[position]['tried'].append(tried)
        if found and not results[position]['suggestion']:
            results[position]['suggestion'] = found

    for position, item in enumerate(items):
        take(position, suggest_from_rule(item['name']), 'rule')
        if allow_peer:
            take(position, suggest_from_peers(index, item['country'], item['name']), 'peer')

    for flag, runner, label in ((allow_local, lambda batch: suggest_with_local_model(batch, local_model or ''), 'local_model'), (allow_ai, suggest_with_claude, 'ai')):
        if not flag:
            continue
        pending = [i for i, row in enumerate(results) if not row['suggestion']]
        if not pending:
            continue
        if label == 'local_model' and not local_model:
            errors.append('Choose a local model to use the local suggestion.')
            continue
        try:
            answers = runner([{**items[i]} for i in pending])
        except Exception as error:  # noqa: BLE001 — shown to the person: credits, Ollama not running ...
            errors.append(f'{label}: {error}')
            continue
        for i, answer in zip(pending, answers):
            take(i, answer, label)

    for row in results:
        if row['suggestion']:
            verdict = check(row['country'], row['name'], row['category'], row['suggestion']['code'], index)
            row['validation'] = verdict
            if verdict['status'] == 'error':  # a suggestion the reference does not know is dropped, not shown as usable
                row['suggestion'] = None
        else:
            row['validation'] = None
    return {'results': results, 'errors': errors}
