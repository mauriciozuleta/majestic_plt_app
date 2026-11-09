"""Check of the normalization module on the USDA retail report PDF (https://www.ams.usda.gov/mnreports/fvwretail.pdf):
`python -m backend.catalog_normalization.evaluate_retail_pdf [--pdf PATH] [--out FILE.json]`

The "NATIONAL CONVENTIONAL SUMMARY" table of the PDF is read (commodity, variety, unit, number of ads, weighted average price), then:
  A. 10 packs that state MORE THAN ONE POUND ("3 lb bag", "5 lb bag", "2 pound bags") — converted from the stated weight, compared with the $/kg worked out by hand;
  B. 10 packs whose unit is NOT a weight ("each", "per bunch", "4 count mesh bags"...) — these need the weight of one item: USDA's published table answers first (no AI); a product it
     has no rule for must say "needs research" (never guess), and with the item weight researched earlier on the web (README.md) the price per kg follows.
The same packs are then looked up in the catalog the app stored from the API (source usa_retail_produce) and their normalized values compared."""

import argparse
import json
import re
import sys
from dataclasses import dataclass

import pdfplumber

from .reference import lookup as reference_lookup
from .service import items_in_weight, normalize_price
from .store import ItemWeight, MemoryStore
from .units import LB_TO_KG, parse_unit

LINE = re.compile(r'^(?P<left>.+?)\s+(?P<ads>\d{1,3}(?:,\d{3})*)\s+(?P<price>\d+\.\d{2})(?:\s|$)')
UNIT = re.compile(r'^(?:per\s+\w+|each|\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\s*(?:-|\s)?(?:lbs?|pounds?|oz|ounces?|count|ct|pints?|quarts?|gallons?|liters?|l|ml|g|kg)\b.*|trays?\b.*|\d+-\d+\s*ct.*)$', re.IGNORECASE)

# Item weights (kg) found by the web research of the 2026-11-07 live evaluation (README.md, "Test results"), keyed by the commodity name USDA uses here.
RESEARCHED = {
    'Pineapples': 1.4, 'Avocados': 0.17, 'Mangoes': 0.30, 'Cantaloupes': 1.4, 'Cilantro': 0.085, 'Cauliflower': 0.65, 'Cucumbers': 0.25,
    'Peppers (Bell Type)': 0.15, 'Lettuce': 0.65, 'Watermelons': 9.0,
}


@dataclass
class Pack:
    name: str
    unit: str
    ads: int
    price: float


def read_packs(path: str) -> list[Pack]:
    packs: list[Pack] = []
    inside = False
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or '').splitlines():
                if line.startswith('NATIONAL CONVENTIONAL SUMMARY'):
                    inside = True
                    continue
                if line.startswith(('NATIONAL ORGANIC', 'REGIONAL', 'REGION ')) or (inside and line.startswith('NATIONAL ') and 'CONVENTIONAL' not in line):
                    inside = False
                if not inside:
                    continue
                match = LINE.match(line)
                if not match:
                    continue
                tokens = match.group('left').split()
                for i in range(1, len(tokens)):
                    if UNIT.match(' '.join(tokens[i:])):
                        packs.append(Pack(' '.join(tokens[:i]), ' '.join(tokens[i:]), int(match.group('ads').replace(',', '')), float(match.group('price'))))
                        break
    return packs


def stated_pounds(unit: str) -> float | None:
    """Pounds written in a unit text — the independent hand reading the module's result is checked against."""
    found = re.match(r'^(\d+(?:\.\d+)?)\s*(?:lb|lbs|pound|pounds)\b', unit, re.IGNORECASE)
    return float(found.group(1)) if found else None


def commodity_of(name: str) -> str:
    return next((c for c in sorted(RESEARCHED, key=len, reverse=True) if name.startswith(c)), name.split()[0])


def pick(packs: list[Pack]):
    heavy, other, seen = [], [], set()
    for pack in packs:
        pounds = stated_pounds(pack.unit)
        commodity = commodity_of(pack.name)
        if pounds and pounds > 1 and commodity not in seen and len(heavy) < 10 and pack.ads >= 20:
            heavy.append(pack)
            seen.add(commodity)
    wanted = list(RESEARCHED)
    for commodity in wanted:
        candidates = [p for p in packs if commodity_of(p.name) == commodity and parse_unit(p.unit, p.name).kind == 'count' and (commodity != 'Lettuce' or 'Iceberg' in p.name)]
        if candidates:
            other.append(max(candidates, key=lambda p: p.ads))
    return heavy, other[:10]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', default='fvwretail.pdf')
    parser.add_argument('--out')
    args = parser.parse_args()
    packs = read_packs(args.pdf)
    print(f'{len(packs)} packs read from the PDF (national, conventional)')
    heavy, other = pick(packs)

    print('\nA - packs of MORE THAN ONE POUND')
    ok_a = 0
    store = MemoryStore()
    report = {'heavy': [], 'unit': []}
    for p in heavy:
        got = normalize_price(commodity_of(p.name), p.unit, p.price, store)
        expected = p.price / (stated_pounds(p.unit) * LB_TO_KG)
        good = got.price_per_kg is not None and abs(got.price_per_kg - expected) / expected < 1e-6
        ok_a += good
        print(f"  {'OK ' if good else 'BAD'} {p.name:<34}{p.unit:<22}${p.price:<6}-> {got.price_per_kg and round(got.price_per_kg, 3)} $/kg (hand: {expected:.3f}) [{got.method}]")
        report['heavy'].append({'name': p.name, 'unit': p.unit, 'price': p.price, 'price_per_kg': got.price_per_kg, 'expected': expected, 'method': got.method, 'ok': good})
    print(f'  {ok_a}/{len(heavy)} correct')

    print('\nB - packs whose unit is NOT a weight')
    ok_b = 0
    for p in other:
        commodity = commodity_of(p.name)
        parsed = parse_unit(p.unit, p.name)
        count = parsed.item_count or 1
        count_unit = 'bunch' if parsed.count_unit == 'bunch' else 'each'
        before = normalize_price(commodity, p.unit, p.price, MemoryStore())  # nothing researched: USDA's table answers, or it must say "needs research"
        if before.method == 'reference_item_weight':
            reference = reference_lookup(commodity, count_unit)
            expected = p.price / (reference.item_kg * count)
            good = before.price_per_kg is not None and abs(before.price_per_kg - expected) / expected < 1e-6 and 'USDA' in before.note
            source, after = f'USDA table ({reference.item_kg * 1000:.0f} g/item)', before
            weight_kg = reference.item_kg
        else:
            store = MemoryStore()
            store.put(ItemWeight(commodity, count_unit, RESEARCHED[commodity], confidence='researched 2026-11-07', note='web research of the live evaluation'))
            after = normalize_price(commodity, p.unit, p.price, store)
            expected = p.price / (RESEARCHED[commodity] * count)
            good = before.method == 'needs_research' and before.price_per_kg is None and after.price_per_kg is not None and abs(after.price_per_kg - expected) / expected < 1e-6
            source, weight_kg = f'researched ({RESEARCHED[commodity] * 1000:.0f} g/item)', RESEARCHED[commodity]
        ok_b += good
        box = items_in_weight(commodity, 10, MemoryStore() if before.method == 'reference_item_weight' else store, count_unit)
        print(f"  {'OK ' if good else 'BAD'} {p.name:<26}{p.unit[:22]:<23}${p.price:<6} {source:<30} x{count:g}: {after.price_per_kg and round(after.price_per_kg, 2)} $/kg | 10 kg box ~ {box and round(box['items'])} items")
        report['unit'].append({'name': p.name, 'unit': p.unit, 'price': p.price, 'method': after.method, 'price_per_kg': after.price_per_kg, 'expected': expected, 'ok': good})
    print(f'  {ok_b}/{len(other)} correct')
    if args.out:
        json.dump(report, open(args.out, 'w', encoding='utf-8'), indent=1)
    return 0 if ok_a == len(heavy) == 10 and ok_b == len(other) == 10 else 1


if __name__ == '__main__':
    sys.exit(main())
