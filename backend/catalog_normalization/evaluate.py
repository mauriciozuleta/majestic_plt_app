"""Live check of the normalization module: `python -m backend.catalog_normalization.evaluate`

Part A — 10 products priced by a STATED weight (real unit strings from the app's catalogs): converted deterministically, compared with the expected $/kg
         worked out by hand.
Part B — 10 products priced by the unit (each / bunch / N count): the weight of one item is researched on the web (one batched call), then compared with a
         plausible range for that product; the two-way conversions are shown (items per 10 kg box, weight of 8 items).

Uses the API key from .env (never printed). Prints a table and writes the research results to a JSON file given with --out."""

import argparse
import json
import sys

from dotenv import load_dotenv

from .service import items_in_weight, normalize_catalog, weight_of_items
from .store import MemoryStore
from .units import LB_TO_KG, OZ_TO_KG

PART_A = [
    # (name, unit text, price, expected $/kg, how the expectation was worked out)
    ('Bananas', 'per lb', 0.61, 0.61 / LB_TO_KG, '0.61 / 0.4536'),
    ('Apples, Cortland', '3 lb bag', 3.61, 3.61 / (3 * LB_TO_KG), '3.61 / (3 x 0.4536)'),
    ('Beans, Round Green', '12 oz bag', 2.92, 2.92 / (12 * OZ_TO_KG), '2.92 / (12 x 0.02835)'),
    ('Blueberries', '1 pint (11-12 oz cntr w/ lid)', 4.76, 4.76 / (11.5 * OZ_TO_KG), 'mid of 11-12 oz'),
    ('Strawberries', 'flats 8 1-lb containers with lids', 28.0, 28.0 / (8 * LB_TO_KG), '28 / (8 lb)'),
    ('Tomatoes, Mature Greens', '25 lb cartons loose', 57.35, 57.35 / (25 * LB_TO_KG), '57.35 / (25 lb)'),
    ('Beef Primal Rib', 'USD/cwt (100lb)', 660.58, 660.58 / (100 * LB_TO_KG), '660.58 / 45.36 kg'),
    ('US #2 Yellow Corn', 'USD/bushel', 5.35, 5.35 / (56 * LB_TO_KG), '5.35 / (56 lb)'),
    ('Papa pastusa', 'bulto de 50 kilos', 90000.0, 90000.0 / 50, '90000 / 50 kg'),
    ('Picsweet Green Peas 340G', 'g', 12.15, 12.15 / 0.34, '12.15 / 0.340 kg'),
]

PART_B = [
    # (name, unit text, price, plausible kg of ONE item (low, high))
    ('Pineapple', 'each', 3.23, (0.9, 2.5)),
    ('Avocado, Hass', '4 count mesh bags', 3.45, (0.14, 0.35)),
    ('Mango', 'each', 1.13, (0.2, 0.7)),
    ('Watermelon', 'each', 5.99, (3.0, 12.0)),
    ('Cantaloupe', 'each', 3.70, (0.8, 2.2)),
    ('Lettuce, Iceberg', 'each', 1.99, (0.45, 1.0)),
    ('Cilantro', 'per bunch', 0.74, (0.04, 0.15)),
    ('Cauliflower', 'each', 3.09, (0.5, 1.6)),
    ('Cucumber, Slicing', 'each', 0.86, (0.2, 0.5)),
    ('Peppers, Bell Type', '3 count filmbag', 3.40, (0.12, 0.30)),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', help='write the part B research results to this JSON file')
    parser.add_argument('--skip-web', action='store_true', help='run part A only')
    args = parser.parse_args()
    load_dotenv()

    print('PART A - established weight (deterministic)')
    store = MemoryStore()
    rows_a = [{'name': n, 'unit': u, 'price': p} for n, u, p, _e, _w in PART_A]
    ok_a = 0
    for row, (_n, _u, _p, expected, how) in zip(normalize_catalog(rows_a, store, allow_research=False), PART_A):
        got = row['normalized']['price_per_kg']
        good = got is not None and abs(got - expected) / expected < 0.005
        ok_a += good
        print(f"  {'OK ' if good else 'BAD'} {row['name']:<28} {row['unit']:<36} -> {got if got is None else round(got, 3)} $/kg (expected {expected:.3f}; {how}) [{row['normalized']['method']}]")
    print(f'  {ok_a}/{len(PART_A)} correct')
    if args.skip_web:
        return 0 if ok_a == len(PART_A) else 1

    print('\nPART B - priced by the unit (web research of one item)')
    rows_b = [{'name': n, 'unit': u, 'price': p} for n, u, p, _r in PART_B]
    out = normalize_catalog(rows_b, store)
    ok_b = 0
    report = []
    for row, (_n, _u, _p, (low, high)) in zip(out, PART_B):
        norm = row['normalized']
        item_kg = norm['item_kg']
        inside = item_kg is not None and low <= item_kg <= high
        ok_b += inside
        box = items_in_weight(row['name'], 10, store, 'bunch' if 'bunch' in row['unit'] else 'each')
        eight = weight_of_items(row['name'], 8, store, 'bunch' if 'bunch' in row['unit'] else 'each')
        print(f"  {'OK ' if inside else 'OUT'} {row['name']:<20} {row['unit']:<18} item {None if item_kg is None else round(item_kg * 1000)} g (plausible {low * 1000:.0f}-{high * 1000:.0f} g)"
              f" -> {None if norm['price_per_kg'] is None else round(norm['price_per_kg'], 2)} $/kg | 10 kg box ~ {None if not box else round(box['items'])} items | 8 items ~ {None if not eight else round(eight['weight_kg'], 1)} kg | {norm['confidence']}")
        print(f"      {norm['note'][:230]}")
        report.append({'name': row['name'], 'unit': row['unit'], 'normalized': norm, 'plausible_item_kg': [low, high], 'inside': inside,
                       'items_per_10kg': None if not box else box['items'], 'weight_of_8_kg': None if not eight else eight['weight_kg']})
    print(f'  {ok_b}/{len(PART_B)} inside the plausible range')
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=1, ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
