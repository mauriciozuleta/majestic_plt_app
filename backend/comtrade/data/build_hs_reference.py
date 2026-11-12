"""Builds the two HS reference files the app reads (run by hand, rarely: python backend/comtrade/data/build_hs_reference.py).

  hs_2022.json      {code: name} of HS 2022 (Comtrade's `H6` revision file), every chapter, heading and subheading: the CURRENT nomenclature, what a product's code must belong to.
  hs_combined.json  {code: name} of every revision merged (Comtrade's `HS` file, H0 to H6): only to NAME the codes of historical trade data (a 2010 trade flow is reported in HS 2007 codes).

Both are Comtrade's public static reference files (no key, no quota; not the trade-data API). They were fetched at build time and are committed, so the app never goes to the
network for an HS code. HS is revised about every 5 years (the next, HS 2027, takes effect on 1 January 2027): rebuild then, with the new revision file added here.
The US Census Schedule B (chapters 1-3 compared on 2026-11-12) has the same 6-digit codes as HS 2022 (325 of 325) plus US-only 10-digit suffixes: no new information at 6 digits."""

import json
from pathlib import Path

import httpx

BASE = 'https://comtradeapi.un.org/files/v1/app/reference/'
HERE = Path(__file__).resolve().parent


def fetch(name: str) -> dict[str, str]:
    rows = httpx.get(f'{BASE}{name}.json', timeout=120, headers={'User-Agent': 'Mozilla/5.0'}).json()['results']
    out = {}
    for row in rows:
        code = row.get('id')
        if not code or code == 'TOTAL':
            continue
        text = row['text']
        out[code] = text[len(f'{code} - '):] if text.startswith(f'{code} - ') else text
    return dict(sorted(out.items()))


if __name__ == '__main__':
    for source, target in (('H6', 'hs_2022.json'), ('HS', 'hs_combined.json')):
        data = fetch(source)
        (HERE / target).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'{target}: {len(data)} codes')
