"""Deterministic reading of a catalog's unit text ("3 lb bag", "per bunch", "6 x 500 g", "flats 8 1-lb containers", "each", "11-12 oz cntr") into
what it really says: a weight, a count of items, a volume, or nothing usable. No network, no guessing — every number returned was written in
the text (or is an official fixed factor), and the `basis` says which.

kinds:
  weight  — the priced unit has a stated weight        -> `weight_kg` (one priced unit)
  count   — the priced unit is N items                  -> `item_count`, `count_unit` ('each', 'bunch', 'head', 'dozen', 'pack' ...)
  volume  — liters, gallons, fl oz ...                  -> `volume_l` (a density is needed to get a weight: not guessed)
  unknown — nothing usable in the text
"""

import re
from dataclasses import dataclass

LB_TO_KG = 0.45359237
OZ_TO_KG = 0.028349523125

# unit word -> kg (singular and plural spellings, English and Spanish)
WEIGHT_FACTORS = {
    'kg': 1.0, 'kgs': 1.0, 'kilo': 1.0, 'kilos': 1.0, 'kilogram': 1.0, 'kilograms': 1.0, 'kilogramo': 1.0, 'kilogramos': 1.0,
    'g': 0.001, 'gr': 0.001, 'gm': 0.001, 'gram': 0.001, 'grams': 0.001, 'gramo': 0.001, 'gramos': 0.001,
    'lb': LB_TO_KG, 'lbs': LB_TO_KG, 'pound': LB_TO_KG, 'pounds': LB_TO_KG, 'libra': LB_TO_KG, 'libras': LB_TO_KG,
    'oz': OZ_TO_KG, 'ounce': OZ_TO_KG, 'ounces': OZ_TO_KG,
    'cwt': 100 * LB_TO_KG,  # hundredweight (US): 100 lb
    'arroba': 25 * LB_TO_KG,  # traditional Colombian unit: 25 lb
}
_WEIGHT_WORDS = '|'.join(sorted(WEIGHT_FACTORS, key=len, reverse=True))

# a number (or a range "11-12") immediately followed by a weight unit; "1-lb" (hyphen between the number and the unit) is allowed
_NUM = r'\d+(?:[.,]\d+)?'
WEIGHT_RE = re.compile(rf'(?P<n>{_NUM})(?:\s*(?:-|–|to)\s*(?P<n2>{_NUM}))?\s*-?\s*(?P<u>{_WEIGHT_WORDS})\b', re.IGNORECASE)
PER_WEIGHT_RE = re.compile(rf'(?:\bper\b|/|\bpor\b)\s*(?P<u>{_WEIGHT_WORDS})\b', re.IGNORECASE)
BARE_WEIGHT_RE = re.compile(rf'^\s*(?P<u>{_WEIGHT_WORDS})\.?\s*$', re.IGNORECASE)

_VOLUME_LITERS = {'ml': 0.001, 'l': 1.0, 'lt': 1.0, 'liter': 1.0, 'liters': 1.0, 'litre': 1.0, 'litres': 1.0, 'gal': 3.785411784, 'gallon': 3.785411784,
                  'gallons': 3.785411784, 'qt': 0.946352946, 'quart': 0.946352946, 'quarts': 0.946352946, 'pt': 0.473176473, 'pint': 0.473176473,
                  'pints': 0.473176473, 'floz': 0.0295735296, 'fl oz': 0.0295735296}
VOLUME_RE = re.compile(rf'(?P<n>{_NUM})?\s*-?\s*(?P<u>fl\.?\s*oz|gallons?|gal|quarts?|qt|pints?|pt|liters?|litres?|ml|lt|l)\b', re.IGNORECASE)

DOZEN_RE = re.compile(r'\b(?:(?P<n>\d+)\s*)?(?:dozen|doz|docena|docenas)\b', re.IGNORECASE)
# "4 count", "36 ct", "100's", "18 pieces", "5 ears", "30 unidades"
COUNT_RE = re.compile(r"(?P<n>\d+)\s*(?:[-]?\s*)(?:count|cnt|ct|pcs|pc|pieces?|units?|unidades|ears?|heads?|bunch(?:es)?|each)\b|(?P<n2>\d+)\s*['’]s\b", re.IGNORECASE)
# "box of 18", "case of 24", "caja de 10", "(10 per package)"
COUNT_OF_RE = re.compile(r'\b(?:box|case|bag|pack|tray|caja|bolsa|paquete|carton)\s+(?:of|de)\s+(?P<n>\d+)\b|\((?P<n2>\d+)\s*per\s*package\)', re.IGNORECASE)
COUNT_WORDS = (
    ('bunch', re.compile(r'\b(?:bunch(?:es)?|bndl\.?|bundle|manojo|atado)\b', re.IGNORECASE)),
    ('head', re.compile(r'\b(?:heads?|cabeza)\b', re.IGNORECASE)),
    ('sleeve', re.compile(r'\bsleeve\b', re.IGNORECASE)),
    ('each', re.compile(r'\b(?:each|ea|unit|unidad|unidades|piece|pc|item|per item|unitario)\b', re.IGNORECASE)),
    ('pack', re.compile(r'\b(?:package|pack|bag|box|bolsa|caja|paquete|tray|carton|case|clamshell|container)\b', re.IGNORECASE)),
)


@dataclass
class ParsedUnit:
    kind: str  # 'weight' | 'count' | 'volume' | 'unknown'
    weight_kg: float | None = None  # kg of ONE priced unit (kind == 'weight')
    item_count: float | None = None  # items in one priced unit (kind == 'count'); None when the text says "a bunch" / "a bag" without a number
    count_unit: str | None = None  # 'each' | 'bunch' | 'head' | 'dozen' | 'sleeve' | 'pack'
    volume_l: float | None = None  # liters of one priced unit (kind == 'volume')
    basis: str = ''  # how it was read, for the note shown to the user
    count_hint: float | None = None  # a count written beside a stated weight ("6 x 500 g" -> 6): useful for items-per-pack


def _num(text: str) -> float:
    return float(text.replace(',', '.'))


def _is_fluid_context(text: str) -> bool:
    return bool(re.search(r'\bfl\.?\s*oz\b|gallon|\bgal\b|quart|\bliter|\blitre|\bml\b|\bpints?\b(?!.*(?:cntr|container|clamshell))', text, re.IGNORECASE))


def _weight_match(text: str):
    """First `number unit` weight in the text -> (kg, matched text, multiplier) — a count written just before it multiplies ("6 x 500 g", "8 1-lb")."""
    for match in WEIGHT_RE.finditer(text):
        unit = match.group('u').lower()
        if unit == 'oz' and _is_fluid_context(text) and not re.search(r'cntr|container|clamshell|package|pkg|bag', text, re.IGNORECASE):
            continue  # "64 oz (1/2 gallon)": fluid ounces
        low = _num(match.group('n'))
        high = _num(match.group('n2')) if match.group('n2') else low
        amount = (low + high) / 2
        multiplier = 1.0
        before = re.search(r'(\d+)\s*(?:[x×*/])?\s*$', text[: match.start()])
        if before and (match.start() - before.start() <= 5):
            multiplier = float(before.group(1))
        return amount * WEIGHT_FACTORS[unit] * multiplier, match.group(0).strip(), multiplier
    return None


def parse_unit(unit_text: str | None, product_name: str = '') -> ParsedUnit:
    """Reads `unit_text` (and, for a bare "kg"/"g" unit, the pack weight the product name states: "Green Peas 340G"). Never guesses."""
    text = (unit_text or '').strip()
    name = (product_name or '').strip()
    if not text:
        found = _weight_match(name)
        if found:
            return ParsedUnit('weight', weight_kg=found[0], basis=f'No unit given; the product name states its weight ("{found[1]}").')
        return ParsedUnit('unknown', basis='No unit reported.')

    # a bare weight unit: the price is per that unit — unless the name states a fixed pack ("340G", "1.4KG"), which is then the priced unit
    if BARE_WEIGHT_RE.match(text):
        unit = BARE_WEIGHT_RE.match(text).group('u').lower()
        pack = _weight_match(name)
        if pack:
            return ParsedUnit('weight', weight_kg=pack[0], basis=f'Priced per pack: the product name states its weight ("{pack[1]}").')
        return ParsedUnit('weight', weight_kg=WEIGHT_FACTORS[unit], basis=f'Priced per {unit} (1 {unit} = {WEIGHT_FACTORS[unit]:.6g} kg).')

    per = PER_WEIGHT_RE.search(text)
    if per and not WEIGHT_RE.search(text):
        unit = per.group('u').lower()
        return ParsedUnit('weight', weight_kg=WEIGHT_FACTORS[unit], basis=f'Priced per {unit} (1 {unit} = {WEIGHT_FACTORS[unit]:.6g} kg).')

    found = _weight_match(text)
    if found:
        kg, matched, multiplier = found
        extra = f' (x{multiplier:g})' if multiplier != 1 else ''
        return ParsedUnit('weight', weight_kg=kg, basis=f'The unit states its weight: "{matched}"{extra} = {kg:.4g} kg.', count_hint=multiplier if multiplier != 1 else None)

    dozen = DOZEN_RE.search(text)
    if dozen:
        n = float(dozen.group('n') or 1) * 12
        return ParsedUnit('count', item_count=n, count_unit='dozen', basis=f'A dozen ("{dozen.group(0)}") = {n:g} items.')
    counted = COUNT_RE.search(text) or COUNT_OF_RE.search(text)
    if counted:
        n = float(next(v for v in counted.groups() if v))
        word = next((name_ for name_, rx in COUNT_WORDS if rx.search(text)), 'pack')
        return ParsedUnit('count', item_count=n, count_unit=word if word != 'each' else 'pack', basis=f'The unit states a count: "{counted.group(0).strip()}" = {n:g} items.')

    volume = VOLUME_RE.search(text) if (_is_fluid_context(text) or VOLUME_RE.fullmatch(text.strip())) else None
    if volume:
        unit = re.sub(r'[\s.]+', '', volume.group('u').lower())  # 'fl. oz' -> 'floz'
        factor = _VOLUME_LITERS.get(unit)
        if factor:
            liters = (_num(volume.group('n')) if volume.group('n') else 1.0) * factor
            return ParsedUnit('volume', volume_l=liters, basis=f'A volume unit ("{text}"): a density is needed to convert it to a weight, so no $/kg is given.')

    for word, rx in COUNT_WORDS:
        if rx.search(text):
            return ParsedUnit('count', item_count=1.0 if word == 'each' else None, count_unit=word, basis=f'A count unit ("{text}") with no weight stated.')

    return ParsedUnit('unknown', basis=f'"{text}" is not a recognised weight, count or volume unit.')
