"""From a portfolio product to its destination tariff line, and from there to the tax multiplier.

A product carries its HS code (the cached classification, see comtrade/product_classification.py). The destination's tariff has one
or several lines under that HS code; this module picks the one that applies, in a fixed order, and says HOW it picked
(`method`) and whether the pick is a judgement call (`status` 'review'):

  1. one line under the HS code, or all lines carry the same rates          -> 'hs' / 'hs-same-rate'          (ok)
  2. a word of the product's name singles out exactly one line's wording    -> 'hs+name'                      (ok)
  3. exactly one catch-all "Other ..." line                                 -> 'catch-all'                    (review)
  4. otherwise the line with the highest tax (a conservative estimate)      -> 'highest-of-N'                 (review)
  no HS code: the best match of the name in the tariff search, always 'review' -> 'name-search'

The multiplier itself is computed by the country's calculator (no model involved):
  tax_multiplier = import taxes / goods value   (2.23 = taxes of 223% of the goods value)
  landed_multiplier = 1 + tax_multiplier        (3.23 = what the goods cost once the taxes are paid, per USD of goods)
It is computed for 1 kg of goods at the product's price, by air, with no freight/insurance (those are another module's job), so only
duties and taxes that scale with the value — or a per-kg duty at the product's own price — are in it; fixed fees are not.
"""

import re

from .base import Calculator, Inputs, digits, query_words

_INDEX: dict[int, tuple[int, dict[str, list[dict]]]] = {}


def lines_for_hs(calculator: Calculator, hs_code: str | None) -> list[dict]:
    """The calculator's tariff lines whose code starts with the HS code (6 digits, or what is given)."""
    code = digits(hs_code or '')
    if len(code) < 4:
        return []
    calculator.info()  # makes sure the data is loaded
    lines = calculator.lines  # type: ignore[attr-defined]
    cached = _INDEX.get(id(calculator))
    if cached is None or cached[0] != len(lines):
        index: dict[str, list[dict]] = {}
        for line in lines:
            index.setdefault(digits(line['code'])[:6], []).append(line)
        _INDEX[id(calculator)] = cached = (len(lines), index)
    index = cached[1]
    if len(code) <= 6:
        return [line for key, group in index.items() if key.startswith(code) for line in group]
    return [line for group in index.values() for line in group if digits(line['code']).startswith(code)]


def _words(text: str) -> set[str]:
    return set(query_words(text))


def choose_line(calculator: Calculator, candidates: list[dict], product_name: str, tax_of) -> tuple[dict, str, str, str]:
    """(line, method, status, note) — see the module docstring. `tax_of(line)` returns the line's tax per USD of goods (used for the fallback)."""
    if len(candidates) == 1:
        return candidates[0], 'hs', 'ok', ''
    if len({calculator.signature(line) for line in candidates}) == 1:  # type: ignore[attr-defined]
        return candidates[0], 'hs-same-rate', 'ok', ''
    wanted = _words(product_name)
    row_words = [_words(line['path']) for line in candidates]
    scores = [sum(1 for word in wanted & words if sum(word in other for other in row_words) == 1) for words in row_words]
    best = max(scores)
    if best > 0 and scores.count(best) == 1:
        return candidates[scores.index(best)], 'hs+name', 'ok', ''
    catch_all = [line for line in candidates if re.match(r'\s*other\b', line['description'], re.IGNORECASE)]
    if len(catch_all) == 1:
        return catch_all[0], 'catch-all', 'review', f'{len(candidates)} tariff lines share the HS code and none names the product; the catch-all line was used.'
    taxed = max(candidates, key=tax_of)
    return taxed, f'highest-of-{len(candidates)}', 'review', f'{len(candidates)} tariff lines share the HS code with different rates and none names the product; the line with the highest tax was used.'


def multiplier_for(calculator: Calculator, product: dict, origin: str | None) -> dict:
    """product: {name, hs_code, price_usd_kg?, category?}. Returns the row stored in product_tax_multipliers (without keys)."""
    name = product['name']
    price = product.get('price_usd_kg')
    goods = price if price and price > 0 else 1.0

    def result_for(line):
        return calculator.calculate(line['code'], Inputs(goods_value_usd=goods, quantity_kg=1.0, origin=origin, transport='air'))

    def tax_of(line):
        return result_for(line).to_dict()['total_tax_usd']

    candidates = lines_for_hs(calculator, product.get('hs_code'))
    if candidates:
        line, method, status, note = choose_line(calculator, candidates, name, tax_of)
    else:
        found = calculator.search(name, 1) if name else []
        if not found:
            return {'status': 'no_line', 'method': None, 'note': f'No tariff line found{"" if product.get("hs_code") else " (the product has no HS code)"}.'}
        line = calculator.by_code.get(found[0]['code']) if hasattr(calculator, 'by_code') else None  # type: ignore[attr-defined]
        if line is None:
            return {'status': 'no_line', 'method': None, 'note': 'No tariff line found.'}
        method, status, note = 'name-search', 'review', 'The product has no HS code, or none of its tariff lines exist in this tariff; the best name match was used.'

    result = result_for(line).to_dict()
    detail = [{'name': tax['name'], 'rate': tax['rate'], 'per_usd': round(tax['amount'] / goods, 6)} for tax in result['taxes'] if not tax['recoverable']]
    has_specific = any('specific' in tax['name'].lower() for tax in result['taxes'])
    if not result['complete']:
        status, note = 'incomplete', (note + ' ' + ' '.join(result['warnings'][:1])).strip()
    elif has_specific and not (price and price > 0):
        status, note = 'needs_price', (note + ' The duty is a fixed amount per unit, so the multiplier depends on the product\'s price, which is not known.').strip()
    multiplier = sum(tax['amount'] for tax in result['taxes'] if not tax['recoverable']) / goods  # from the unrounded amounts
    return {
        'status': status,
        'method': method,
        'note': note,
        'tariff_code': line['code'],
        'tariff_path': line['path'],
        'tax_multiplier': None if status in ('needs_price',) else round(multiplier, 4),
        'landed_multiplier': None if status in ('needs_price',) else round(1 + multiplier, 4),
        'detail': detail,
    }
