"""Checks a proposed item weight (typed by a person or suggested by the AI) before it is saved. Nothing here calls the network.

A weight is `error` when it cannot be right (zero, or outside any plausible range for that unit), `warning` when it is suspicious (it disagrees with USDA's published weight,
with the typical range the AI gave, or it makes the product cost far more or less per kilo than the same product listed with a weight in the same source), and `ok` otherwise.
Every result also carries the price per kg it would produce for the product's own listings, so the person sees the consequence of the number."""

from dataclasses import dataclass, field
from statistics import median

from .reference import lookup as reference_lookup
from .units import parse_unit

# plausible weight of ONE priced item, kg, by unit
BOUNDS_KG = {'each': (0.002, 40.0), 'bunch': (0.02, 3.0), 'head': (0.1, 6.0), 'sleeve': (0.05, 2.0), 'dozen': (0.2, 6.0), 'pack': (0.01, 25.0)}
REFERENCE_BAND = (0.5, 2.0)  # a weight outside half to double of USDA's is flagged
PEER_BAND = (0.25, 4.0)  # a price per kg outside a quarter to four times the same product's listed price per kg is flagged


@dataclass
class Validation:
    status: str = 'ok'  # 'ok' | 'warning' | 'error'
    messages: list[str] = field(default_factory=list)
    previews: list[dict] = field(default_factory=list)  # [{label, price_per_kg}] the listings converted with this weight

    def add(self, level: str, message: str) -> None:
        self.messages.append(message)
        if level == 'error' or (level == 'warning' and self.status == 'ok'):
            self.status = level

    def to_dict(self) -> dict:
        return {'status': self.status, 'messages': self.messages, 'previews': self.previews}


def validate_weight(name: str, count_unit: str, weight_kg: float | None, *, min_kg: float | None = None, max_kg: float | None = None,
                    examples: list[dict] | None = None, peers: list[dict] | None = None) -> Validation:
    """examples: the product's own unit-priced listings [{label, price, unit_text, source}]; peers: the SAME product listed with a weight [{source, per_kg}]. Prices are only ever
    compared inside one group of sources that share a currency (the two Colombian markets, the USDA reports): a peso price and a dollar price are never mixed."""
    result = Validation()
    if weight_kg is None or weight_kg <= 0:
        result.add('error', 'Enter a weight above zero.')
        return result
    low, high = BOUNDS_KG.get(count_unit, BOUNDS_KG['each'])
    if not low <= weight_kg <= high:
        result.add('error', f'{weight_kg * 1000:,.0f} g is not plausible for one {count_unit} (expected {low * 1000:,.0f} g to {high * 1000:,.0f} g).')
    if min_kg and max_kg and not min_kg <= weight_kg <= max_kg:
        result.add('warning', 'The weight is outside the typical range given with it.')
    if min_kg and max_kg and min_kg > max_kg:
        result.add('error', 'The low end of the range is above the high end.')

    reference = reference_lookup(name, count_unit)
    if reference is not None and reference.item_kg:
        ratio = weight_kg / reference.item_kg
        if not REFERENCE_BAND[0] <= ratio <= REFERENCE_BAND[1]:
            result.add('warning', f"USDA's published weight for this product is about {reference.item_kg * 1000:,.0f} g; this value is {ratio:.1f}x that.")

    mine_by_group: dict[str, list[float]] = {}
    for example in examples or []:
        count = parse_unit(example.get('unit_text'), name).item_count or 1
        price = example.get('price')
        if price is None:
            continue
        per_kg = price / (weight_kg * count)
        mine_by_group.setdefault(example.get('group') or example.get('source') or '', []).append(per_kg)
        result.previews.append({'label': example.get('label') or name, 'source': example.get('source') or '', 'price_per_kg': per_kg})
    for group, values in mine_by_group.items():
        theirs = [peer['per_kg'] for peer in peers or [] if (peer.get('group') or peer['source']) == group]
        if not theirs:
            continue
        mine, usual = median(values), median(theirs)
        if usual > 0 and not PEER_BAND[0] <= mine / usual <= PEER_BAND[1]:
            result.add('warning', f'With this weight the product costs {mine:,.2f} per kg ({group}), but the same product listed with a weight there costs about {usual:,.2f} per kg.')
    return result
