"""The normalization entry points.

  normalize_price(...)   one catalog row (name, unit text, price) -> price per kg, pack weight, items per pack, with how it was obtained
  normalize_catalog(...) a whole catalog: finds every distinct (product, count unit) it cannot convert yet, researches them on the web in batches,
                         stores them, then normalizes every row — the function a downloaded catalog goes through before the app uses it
  items_in_weight(...)   "a 10 kg box of avocados holds about 50"        (kg  -> count)
  weight_of_items(...)   "8 pineapples weigh about 12 kg"                (count -> kg)

Rules: a weight written in the data is used as written; official fixed factors (USDA egg dozen weights, bushel test weights) are used as such and
labelled official; everything else that needs the weight of an item comes from the researched store, labelled with its confidence and sources.
Nothing is guessed — a row that cannot be converted says why."""

import re
from dataclasses import asdict, dataclass, field

from .reference import lookup as reference_lookup
from .researcher import MAX_ITEMS_PER_BATCH, research_item_weights
from .store import PRICED_UNIT, ItemWeight, product_key
from .units import OZ_TO_KG, LB_TO_KG, ParsedUnit, parse_unit

# USDA AMS minimum net weight per dozen, by egg size class (oz) — same table as the frontend's unitConversion.js EGG_DOZEN_OZ
EGG_DOZEN_OZ = (('jumbo', 30), ('extra large', 27), ('large', 24), ('medium', 21), ('small', 18), ('peewee', 15))
DEFAULT_EGG_SIZE = 'large'
# USDA standard test weight per bushel (lb)
BUSHEL_LB = (('corn', 56), ('soybean', 60), ('wheat', 60))

COUNT_UNITS_WITH_OWN_WEIGHT = ('bunch', 'head', 'sleeve')  # the weight of one such unit is researched directly


@dataclass
class NormalizedPrice:
    price_per_kg: float | None
    pack_weight_kg: float | None  # weight of ONE priced unit
    items_per_pack: float | None  # items in one priced unit (when known)
    item_kg: float | None  # weight of one item (when known)
    price_per_item: float | None
    method: str  # 'stated_weight' | 'official_factor' | 'reference_item_weight' (USDA table) | 'researched_item_weight' | 'needs_research' | 'unconvertible'
    confidence: str  # 'stated' | 'official' | 'high' | 'medium' | 'low' | 'none'
    note: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _is_egg(name: str) -> bool:
    return bool(re.search(r'\begg|\bhuevo', name or '', re.IGNORECASE))


def _egg_dozen_kg(name: str) -> tuple[float, str, bool]:
    lowered = (name or '').lower()
    for size, oz in EGG_DOZEN_OZ:
        if size in lowered:
            return oz * OZ_TO_KG, size, False
    oz = dict(EGG_DOZEN_OZ)[DEFAULT_EGG_SIZE]
    return oz * OZ_TO_KG, DEFAULT_EGG_SIZE, True


def research_target(name: str, parsed: ParsedUnit) -> tuple[str, str] | None:
    """(product, count unit) whose single-item weight a count unit needs, or None when the unit needs no item weight."""
    if parsed.kind != 'count':
        return None
    if _is_egg(name) and parsed.count_unit in ('dozen', 'each', 'pack'):
        return None  # official USDA factor, no research
    unit = parsed.count_unit if parsed.count_unit in COUNT_UNITS_WITH_OWN_WEIGHT else 'each'
    return name, unit


def normalize_price(name: str, unit_text: str | None, price: float | None, store, *, parsed: ParsedUnit | None = None, researchable: bool = True) -> NormalizedPrice:
    """Uses only what is already known (the text and the store) — it never calls the web; see normalize_catalog for that."""
    parsed = parsed or parse_unit(unit_text, name)
    if price is None:
        return NormalizedPrice(None, None, None, None, None, 'unconvertible', 'none', 'No price.')

    if re.search(r'bushel|\bbu\b', unit_text or '', re.IGNORECASE):
        for grain, lb in BUSHEL_LB:
            if grain in (name or '').lower():
                kg = lb * LB_TO_KG
                return NormalizedPrice(price / kg, kg, None, None, None, 'official_factor', 'official', f'USDA standard test weight for {grain}: {lb} lb/bushel = {kg:.3f} kg.')

    if parsed.kind == 'weight' and parsed.weight_kg:
        return NormalizedPrice(price / parsed.weight_kg, parsed.weight_kg, parsed.count_hint, None, None, 'stated_weight', 'stated', parsed.basis)

    if parsed.kind == 'volume':
        return NormalizedPrice(None, None, None, None, None, 'unconvertible', 'none', parsed.basis)

    if parsed.kind == 'count':
        if _is_egg(name):
            dozen_kg, size, assumed = _egg_dozen_kg(name)
            count = parsed.item_count or 1
            pack_kg = dozen_kg / 12 * count
            note = f'USDA minimum net weight for {size} eggs: {dozen_kg / OZ_TO_KG:.0f} oz/dozen = {dozen_kg:.3f} kg.' + (' Size not stated: "large" assumed.' if assumed else '')
            return NormalizedPrice(price / pack_kg, pack_kg, count, dozen_kg / 12, price / count, 'official_factor', 'official' if not assumed else 'medium', note)
        whole = store.get(name, PRICED_UNIT)
        if whole is not None and whole.item_kg:
            return NormalizedPrice(price / whole.item_kg, whole.item_kg, parsed.item_count, None, None, 'researched_item_weight', whole.confidence or 'low',
                                   f'{parsed.basis} The whole priced unit weighs about {whole.item_kg * 1000:.0f} g ({whole.confidence or "low"} confidence): {whole.note}', whole.sources)
        target = research_target(name, parsed)
        entered = store.get(*target) if target else None
        if entered is not None and entered.confidence == 'user' and entered.item_kg:  # a weight a person typed wins over everything else
            count = parsed.item_count or 1
            pack_kg = entered.item_kg * count
            return NormalizedPrice(price / pack_kg, pack_kg, count, entered.item_kg, price / count, 'researched_item_weight', 'user', f'{parsed.basis} {entered.note}', entered.sources)
        reference = reference_lookup(*target) if target else None  # published data (USDA) before anything researched
        if reference is not None:
            count = parsed.item_count or 1
            pack_kg = reference.item_kg * count
            note = f'{parsed.basis} {reference.note}'
            return NormalizedPrice(price / pack_kg, pack_kg, count, reference.item_kg, price / count, 'reference_item_weight', reference.confidence or 'medium', note, reference.sources)
        record = store.get(*target) if target else None
        if record is None and not researchable:
            return NormalizedPrice(None, None, parsed.item_count, None, None, 'unconvertible', 'none',
                                   f'{parsed.basis} A packaged product with no weight stated in its unit or name: not researched (only fresh-food products are).')
        if record is None:
            return NormalizedPrice(None, None, parsed.item_count, None, None, 'needs_research', 'none', f'{parsed.basis} The weight of one {target[1] if target else "item"} of "{name}" has not been researched yet.')
        if not record.item_kg:
            return NormalizedPrice(None, None, parsed.item_count, None, None, 'unconvertible', 'none', f'Researched, but no reliable weight was found: {record.note}', record.sources)
        count = parsed.item_count or 1
        pack_kg = record.item_kg * count
        note = f'{parsed.basis} One {"item" if target[1] == "each" else target[1]} of {product_key(name)} weighs about {record.item_kg * 1000:.0f} g ({record.confidence or "?"} confidence): {record.note}'
        return NormalizedPrice(price / pack_kg, pack_kg, count, record.item_kg, price / count, 'researched_item_weight', record.confidence or 'low', note, record.sources)

    return NormalizedPrice(None, None, None, None, None, 'unconvertible', 'none', parsed.basis)


def normalize_catalog(rows: list[dict], store, *, research=research_item_weights, allow_research: bool = True, name_key: str = 'name', unit_key: str = 'unit',
                      price_key: str = 'price') -> list[dict]:
    """rows: [{name, unit, price, ...}] -> the same rows with a `normalized` dict added (NormalizedPrice). Count-unit products with no stored item weight are
    researched on the web in batches (once each, then stored); set allow_research=False to only use what the store already holds."""
    parsed_rows = [parse_unit(row.get(unit_key), row.get(name_key) or '') for row in rows]
    if allow_research:
        missing: dict[tuple[str, str], str] = {}
        for row, parsed in zip(rows, parsed_rows):
            target = research_target(row.get(name_key) or '', parsed)
            if target and store.get(*target) is None:
                missing.setdefault((product_key(target[0]), target[1]), row.get(name_key) or '')
        pending = [(name, unit) for (_key, unit), name in missing.items()]
        for start in range(0, len(pending), MAX_ITEMS_PER_BATCH):
            batch = pending[start : start + MAX_ITEMS_PER_BATCH]
            for weight in research([(name, unit, '') for name, unit in batch]):
                store.put(weight)
    out = []
    for row, parsed in zip(rows, parsed_rows):
        out.append({**row, 'normalized': normalize_price(row.get(name_key) or '', row.get(unit_key), row.get(price_key), store, parsed=parsed).to_dict()})
    return out


def _item_weight(name: str, store, count_unit: str = 'each') -> ItemWeight | None:
    reference = reference_lookup(name, count_unit)
    if reference is not None:
        return reference
    record = store.get(name, count_unit)
    return record if record and record.item_kg else None


def items_in_weight(name: str, weight_kg: float, store, count_unit: str = 'each') -> dict | None:
    """How many items of `name` a box of `weight_kg` holds, e.g. a 10 kg box of avocados -> about 50. None when the item weight is not known yet."""
    record = _item_weight(name, store, count_unit)
    if record is None:
        return None
    result = {'items': weight_kg / record.item_kg, 'item_kg': record.item_kg, 'confidence': record.confidence, 'sources': record.sources}
    if record.item_kg_min and record.item_kg_max:
        result['items_range'] = (weight_kg / record.item_kg_max, weight_kg / record.item_kg_min)
    return result


def weight_of_items(name: str, count: float, store, count_unit: str = 'each') -> dict | None:
    """What `count` items of `name` weigh, e.g. 8 pineapples -> about 12 kg."""
    record = _item_weight(name, store, count_unit)
    if record is None:
        return None
    result = {'weight_kg': count * record.item_kg, 'item_kg': record.item_kg, 'confidence': record.confidence, 'sources': record.sources}
    if record.item_kg_min and record.item_kg_max:
        result['weight_range_kg'] = (count * record.item_kg_min, count * record.item_kg_max)
    return result
