"""Builds data/usda_sr28_produce.json from USDA's National Nutrient Database for Standard Reference, release 28 (public domain,
https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR/SR28/dnload/sr28asc.zip): `python -m backend.catalog_normalization.build_usda_reference [--zip PATH]`.

Kept: the fruit, vegetable, herb/spice, nut and legume foods (food groups 0900, 1100, 0200, 1200, 1600) with, for each, its refuse percentage (peel, core, seed,
stem: the part that is thrown away) and its household-measure weights ("1 fruit = 905 g", "1 bunch = 340 g"). USDA's portion weights describe the EDIBLE part, so the
weight of the item as it is bought is `grams / (1 - refuse/100)`. The file is committed; this script only needs to run again for a newer release."""

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path

URL = 'https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR/SR28/dnload/sr28asc.zip'
OUT = Path(__file__).resolve().parent / 'data' / 'usda_sr28_produce.json'
GROUPS = {'0900': 'fruit', '1100': 'vegetable', '0200': 'herb/spice', '1200': 'nut', '1600': 'legume'}


def rows(archive: zipfile.ZipFile, name: str):
    for line in archive.read(name).decode('latin-1').splitlines():
        yield [field.strip('~') for field in line.split('^')]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', help='a local copy of sr28asc.zip')
    args = parser.parse_args()
    data = Path(args.zip).read_bytes() if args.zip else urllib.request.urlopen(URL, timeout=180).read()
    archive = zipfile.ZipFile(io.BytesIO(data))
    foods = {}
    for r in rows(archive, 'FOOD_DES.txt'):
        ndb, group, long_desc, _short, common, _manu, _survey, ref_desc, refuse = r[:9]
        if group in GROUPS:
            foods[ndb] = {'desc': long_desc, 'common': common, 'group': GROUPS[group], 'refuse_pct': float(refuse) if refuse else 0.0, 'refuse_desc': ref_desc, 'portions': []}
    for r in rows(archive, 'WEIGHT.txt'):
        ndb, _seq, amount, description, grams = r[:5]
        if ndb in foods and grams:
            foods[ndb]['portions'].append([description, float(grams), float(amount or 1)])
    foods = {ndb: food for ndb, food in foods.items() if food['portions']}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({'source': 'USDA National Nutrient Database for Standard Reference, Release 28 (2015)', 'foods': foods}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(foods)} foods with portions -> {OUT} ({OUT.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
