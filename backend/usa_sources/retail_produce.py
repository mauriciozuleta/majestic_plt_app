"""US retail produce prices: USDA AMS "Weekly Grocery Store Specialty Crops Feature Activity" (MARS report FVWRETAIL, slug 3324;
https://www.ams.usda.gov/mnreports/fvwretail.pdf is the same report as a PDF).

Each weekly row is a pack of a commodity ("Apples, AMBROSIA, 3 lb bag", "Bananas, per lb", "Avocados, HASS, 4 count mesh bags") with the store-count weighted average of the
advertised prices of that week, nationally and by region. They are retail ADVERTISED (feature) prices, so they run below normal shelf prices, and they are retail, not
wholesale — the product source is registered as "retail" so Market Opportunities flags a wholesale-against-retail comparison.

fetch_retail_produce_products() returns the DETAIL rows (one per pack, flagged `detail`) for the latest week: national, conventional (organic is a different
product), fruit/vegetables/potatoes and onions only. The catalog normalization module converts every pack to $/kg when the catalog is stored, and
consolidate() then builds ONE row per commodity — the store-weighted average $/kg over its convertible packs — which is what the price comparison reads."""

from collections import defaultdict

from .mars import fetch_report

SLUG = 'FVWRETAIL'
REPORT_NAME = 'USDA AMS Weekly Grocery Store Specialty Crops Feature Activity (MARS FVWRETAIL)'
COMMUNITIES = {'Fruit', 'Vegetables', 'Potatoes & Onions'}
REGION = 'National'
CATEGORY = 'Retail Produce'
SOURCE_KEY = 'usa_retail_produce'


def _week_key(date_text: str) -> tuple:
    month, day, year = date_text.split('/')
    return int(year), int(month), int(day)


def _is_food_pack(row: dict) -> bool:
    commodity = (row.get('commodity') or '')
    return row.get('community') in COMMUNITIES and 'processed' not in commodity.lower() and (row.get('organic') or 'No') == 'No'


def fetch_retail_produce_products() -> list[dict]:
    sections = fetch_report(SLUG, days=21)
    rows = next((rows for name, rows in sections.items() if name != 'Report Header' and rows and 'wtd_avg_price' in rows[0]), [])
    rows = [row for row in rows if row.get('region') == REGION and row.get('report_begin_date')]
    if not rows:
        raise RuntimeError('The retail produce report has no national rows in the last three weeks.')
    latest = max((row['report_begin_date'] for row in rows), key=_week_key)
    products = []
    for row in rows:
        if row['report_begin_date'] != latest or not _is_food_pack(row) or not isinstance(row.get('wtd_avg_price'), (int, float)):
            continue
        variety = (row.get('variety') or '').strip()
        size = (row.get('size') or '').strip()
        products.append({
            'category': CATEGORY,
            'product_en': row['commodity'] if variety in ('', 'N/A') else f"{row['commodity']} ({variety.title()})",
            'commodity': row['commodity'],
            'price': float(row['wtd_avg_price']),
            'unit': f'USD/{size}' if size else 'USD/each',
            'detail': True,
            'store_count': row.get('store_count'),
            'prior_week_price': row.get('prior_WK_wtd_avg_price'),
            'prior_year_price': row.get('prior_YR_wtd_avg_price'),
            'source_date': row.get('report_end_date') or latest,
            'report': REPORT_NAME,
            'quality_note': 'Advertised retail price, national store-weighted average, conventional.',
        })
    return products


def consolidate(details: list[dict]) -> list[dict]:
    """One row per commodity: the store-count weighted mean of the packs' $/kg (those the normalization module could convert), in USD/kg. A commodity with no
    convertible pack gets no row (it is listed in the packs, with the reason, until its item weights are researched)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for product in details:
        norm = product.get('norm') or {}
        if isinstance(norm.get('price_per_kg'), (int, float)):
            groups[product['commodity']].append(product)
    consolidated = []
    for commodity, packs in groups.items():
        weights = [float(pack.get('store_count') or 1) for pack in packs]
        per_kg = [pack['norm']['price_per_kg'] for pack in packs]
        average = sum(w * p for w, p in zip(weights, per_kg)) / sum(weights)
        methods = sorted({pack['norm']['method'] for pack in packs})
        consolidated.append({
            'category': CATEGORY,
            'product_en': commodity,
            'price': round(average, 4),
            'unit': 'USD/kg',
            'consolidated': True,
            'pack_rows': len(packs),
            'store_count': int(sum(weights)),
            'price_low_per_kg': round(min(per_kg), 4),
            'price_high_per_kg': round(max(per_kg), 4),
            'source_date': packs[0]['source_date'],
            'report': REPORT_NAME,
            'quality_note': f'Store-weighted average of {len(packs)} advertised retail pack price{"s" if len(packs) != 1 else ""} (national, conventional), converted to USD/kg '
                            f'({", ".join(methods)}); range {min(per_kg):.2f}-{max(per_kg):.2f} USD/kg.',
        })
    return sorted(consolidated, key=lambda row: row['product_en'])
