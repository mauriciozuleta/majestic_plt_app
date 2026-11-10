"""The data the Market Access Brief is written from, built on the server (no browser): our source-country portfolio grouped by HS heading, and — read-only — what Market
Opportunities has measured for the pair. The brief does NOT judge price competitiveness (that is computed numerically elsewhere: Market Opportunities, tax multipliers,
the Shipment Builder); it assesses ACCESS — bans, restrictions, seasonal rules, agreements — per HS heading, which the tax calculators do not cover."""

import json
from collections import Counter, defaultdict

from .. import models
from ..catalog_normalization import hs_store
from ..comtrade import classification

MAX_NAMES = 8
MAX_CODES = 4


def portfolio_by_heading(db, country: str) -> dict:
    """{country, product_count, headings: [{heading, description, count, names, codes, heading_only, unreviewed}], no_code: {count, names}} for one country's stored catalogs."""
    groups: dict[str, dict] = defaultdict(lambda: {'names': [], 'codes': [], 'heading_only': 0, 'unreviewed': 0})
    no_code: list[str] = []
    total = 0
    for item in hs_store.catalog_products(db).values():
        if (item['country'] or '').lower() != country.lower():
            continue
        total += 1
        block = item['hs'] or {}
        if not block.get('hs6'):
            no_code.append(item['name'])
            continue
        group = groups[block['hs6'][:4]]
        group['names'].append(item['name'])
        if block.get('code') and block['code'] not in group['codes']:
            group['codes'].append(block['code'])
        group['heading_only'] += 1 if block.get('label') == 'heading_only' else 0
        group['unreviewed'] += 1 if block.get('ai_suggested') else 0
    headings = [
        {'heading': heading, 'description': classification.hs_name(heading), 'count': len(group['names']), 'names': sorted(group['names'], key=str.lower), 'codes': sorted(group['codes']),
         'heading_only': group['heading_only'], 'unreviewed': group['unreviewed']}
        for heading, group in sorted(groups.items())
    ]
    return {'country': country, 'product_count': total, 'headings': headings, 'no_code': {'count': len(no_code), 'names': sorted(no_code, key=str.lower)}}


def comparison_facts(db, source: str, target: str) -> dict | None:
    """What the saved Market Opportunities comparison of the pair says, per heading — counts and rating names only, no prices. None when nothing was saved."""
    rows = db.query(models.MarketOpportunityComparison).filter_by(source_country=source, target_country=target).all()
    if not rows:
        return None
    per_heading: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        per_heading[(row.hs_code or '')[:4] or 'uncoded'][row.opportunity_rating or 'not rated'] += 1
    calculated = min(row.calculated_at for row in rows if row.calculated_at)
    fetched = [snapshot.fetched_at for snapshot in db.query(models.PriceComparisonSnapshot).all() if snapshot.fetched_at and _belongs_to(db, snapshot.source, source)]
    return {'calculated_at': calculated, 'matched': len(rows), 'stale': bool(fetched) and max(fetched) > calculated,
            'catalogs_refreshed_at': max(fetched) if fetched else None, 'headings': {heading: dict(counts) for heading, counts in sorted(per_heading.items())}}


def _belongs_to(db, snapshot_source: str, country: str) -> bool:
    from ..catalog_normalization.catalog import country_of_source

    return (country_of_source(db, snapshot_source) or '').lower() == country.lower()


def render(pack: dict, facts: dict | None) -> str:
    lines = []
    for entry in pack['headings']:
        flags = []
        if entry['heading_only']:
            flags.append(f"{entry['heading_only']} coded to the heading only")
        if entry['unreviewed']:
            flags.append(f"{entry['unreviewed']} codes not yet reviewed by a person")
        extra = f" [{'; '.join(flags)}]" if flags else ''
        shown = ', '.join(entry['names'][:MAX_NAMES]) + (f", and {entry['count'] - MAX_NAMES} more" if entry['count'] > MAX_NAMES else '')
        lines.append(f"- HS {entry['heading']} {entry['description']}: {entry['count']} product{'s' if entry['count'] != 1 else ''}{extra} (e.g. {shown}; codes {', '.join(entry['codes'][:MAX_CODES])})")
    portfolio = '\n'.join(lines) or '- (no product has an HS code yet)'
    missing = pack['no_code']
    gap = (f"\n\n{missing['count']} products have NO HS code yet, so their access cannot be assessed: {', '.join(missing['names'][:MAX_NAMES])}"
           + (f", and {missing['count'] - MAX_NAMES} more." if missing['count'] > MAX_NAMES else '.')) if missing['count'] else ''
    reference = ''
    if facts:
        per = '\n'.join(f"  - HS {heading}: {', '.join(f'{count} {rating}' for rating, count in counts.items())}" for heading, counts in facts['headings'].items())
        stale = f" WARNING: our catalogs were refreshed on {facts['catalogs_refreshed_at'][:10]}, after this comparison, so it may be out of date." if facts['stale'] else ''
        reference = (f"\n\nFor reference only (measured by our own system; do not restate or recompute any price, and do not judge price competitiveness): our saved Market Opportunities "
                     f"comparison of these two countries, calculated {facts['calculated_at'][:10]}, matched {facts['matched']} products to local products, rated by heading:\n{per}{stale}")
    return portfolio + gap + reference
