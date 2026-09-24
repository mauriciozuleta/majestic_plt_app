"""Reader for the Jamaica Ministry of Agriculture's weekly commodity price
spreadsheets (https://moa.gov.jm/document-categories/commodity-prices).

The page lists the current week's six workbooks — file names carry the date,
so links are discovered from the page each time rather than hardcoded:

  Wholesale        Kingston supermarket purchase prices: Lowest / Highest / Most Frequent
  Retail           Kingston supermarket prices (produce): one "Average Price" column
  Retail Meat      same, for meat, with section rows (BEEF CUTS, ...)
  Farmgate         one Low / High / Most Frequent block per parish
  Urban Municipal  one Low / High / Most Frequent block per market
  Rural Municipal  same, for rural markets

Each row is a commodity with a "Variety/Source" (Local / Imported / a brand),
which is kept in the product name — "Broccoli (Imported)" and "Broccoli
(Local)" are different products with different prices. For the per-market
reports the price is the average of the markets' "Most Frequent" prices, with
the lowest Low and highest High across them kept as a range. Unit and
currency come from each sheet's own title ("Retail Prices (J$/Kg)").

Categories are prefixed with the report ("Farmgate Produce", "Retail Meat —
Beef Cuts") so a price level is never averaged with another one.
"""

import re
from urllib.parse import unquote, urljoin, urlparse

import httpx

from ..price_sources.text_normalize import normalize_id

HOST = 'moa.gov.jm'

# (filename fragment, report label, category label). Longest fragments first
# so "Retail Meat" is matched before "Retail".
REPORTS = [
    ('retail meat', 'Retail Meat', 'Retail Meat'),
    ('urban municipal', 'Urban Municipal', 'Urban Municipal Produce'),
    ('rural municipal', 'Rural Municipal', 'Rural Municipal Produce'),
    ('farmgate', 'Farmgate', 'Farmgate Produce'),
    ('wholesale', 'Wholesale', 'Wholesale Produce'),
    ('retail', 'Retail', 'Retail Produce'),
]

_MONEY = re.compile(r'\(\s*(J\$|US\$|\$)\s*/\s*(kg|lb|lbs)\s*\)', re.IGNORECASE)
_WEEK = re.compile(r'week\s+ending\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})', re.IGNORECASE)
_CURRENCIES = {'J$': 'JMD', 'US$': 'USD', '$': 'USD'}


def matches(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return host == HOST or host.endswith('.' + HOST)


def _report_for(filename: str):
    lowered = unquote(filename).lower()
    for fragment, label, category in REPORTS:
        if fragment in lowered:
            return label, category
    return None


def _number(value):
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    return None  # '-', 'N/A', blank, text


def _text(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _sheet_info(rows: list[list]) -> tuple[str, str, str]:
    """(currency, unit, week ending) read from the sheet's title rows."""
    currency, unit, week = 'JMD', 'kg', ''
    for row in rows[:8]:
        line = ' '.join(_text(cell) for cell in row if cell)
        money = _MONEY.search(line)
        if money:
            currency = _CURRENCIES.get(money.group(1).upper(), 'JMD')
            unit = money.group(2).lower().rstrip('s')
        found = _WEEK.search(line)
        if found:
            week = found.group(1)
    return currency, unit, week


def _find_header(rows: list[list]) -> int | None:
    for index, row in enumerate(rows[:15]):
        if _text(row[0] if row else '').lower() == 'commodity':
            return index
    return None


def _product(commodity, variety, category, unit, currency, week, price, low=None, high=None, markets=None) -> dict:
    name = f'{commodity} ({variety})' if variety else commodity
    product = {
        'id': normalize_id(name),
        'category': category,
        'name': name,
        'unit': unit,
        'price': price,
        'currency': currency,
        'as_of': week,
    }
    if low is not None:
        product['low'] = low
    if high is not None:
        product['high'] = high
    if markets:
        product['markets'] = markets
    return product


def _parse_sheet(rows: list[list], category: str) -> list[dict]:
    header_at = _find_header(rows)
    if header_at is None:
        return []
    currency, unit, week = _sheet_info(rows)
    header = [_text(cell).lower() for cell in rows[header_at]]
    sub = [_text(cell).lower() for cell in (rows[header_at + 1] if header_at + 1 < len(rows) else [])]

    # Columns whose sub-header says "most frequent" mark one market/parish block each.
    frequent = [i for i, cell in enumerate(sub) if 'frequent' in cell and i >= 2]
    flat_price = next((i for i, cell in enumerate(header) if 'most frequent' in cell), None)
    if flat_price is None:
        flat_price = next((i for i, cell in enumerate(header) if 'average' in cell), None)

    products: list[dict] = []
    section = ''

    # Rows under the header that aren't products (a Low/High sub-header, the
    # retail store-name row) have no numeric price and fall out below.
    for row in rows[header_at + 1:]:
        cells = list(row) + [None] * max(0, (max(frequent) if frequent else (flat_price or 0)) + 1 - len(row))
        commodity = _text(cells[0])
        variety = _text(cells[1]) if len(cells) > 1 else ''
        if not commodity:
            continue
        others = [c for c in cells[1:] if c not in (None, '')]
        if not others and commodity.isupper():
            section = commodity.title()  # e.g. "BEEF CUTS" in the meat sheet
            continue

        cat = f'{category} — {section}' if section else category
        if frequent:
            # Per-market blocks: Low is two columns before Most Frequent, High one before.
            prices = [_number(cells[i]) for i in frequent]
            lows = [_number(cells[i - 2]) for i in frequent if i - 2 >= 2]
            highs = [_number(cells[i - 1]) for i in frequent if i - 1 >= 2]
            prices = [p for p in prices if p is not None]
            if not prices:
                continue
            lows = [v for v in lows if v is not None]
            highs = [v for v in highs if v is not None]
            products.append(
                _product(
                    commodity, variety, cat, unit, currency, week,
                    round(sum(prices) / len(prices), 2),
                    low=min(lows) if lows else None,
                    high=max(highs) if highs else None,
                    markets=len(prices),
                )
            )
        elif flat_price is not None:
            price = _number(cells[flat_price])
            if price is None:
                continue
            low = high = None
            if 'most frequent' in header[flat_price]:  # Wholesale: has Lowest / Highest beside it
                low = _number(cells[flat_price - 2]) if flat_price >= 2 else None
                high = _number(cells[flat_price - 1]) if flat_price >= 1 else None
            products.append(_product(commodity, variety, cat, unit, currency, week, price, low=low, high=high))
    return products


def _parse_workbook(content: bytes, category: str) -> list[dict]:
    import openpyxl

    from ..price_sources.la_mayorista import _strip_defined_names

    workbook = openpyxl.load_workbook(_strip_defined_names(content), data_only=True, read_only=True)
    try:
        products: list[dict] = []
        for sheet in workbook.worksheets:
            products.extend(_parse_sheet([list(row) for row in sheet.iter_rows(values_only=True)], category))
        return products
    finally:
        workbook.close()


def analyze(client: httpx.Client, page_url: str, links: list[str]) -> tuple[list[dict], str]:
    """(products, note) from every price workbook the page currently links to.
    Empty products means this reader found nothing — the caller falls back to
    the generic analysis."""
    seen: set[str] = set()
    products: list[dict] = []
    loaded: list[str] = []
    for href in links:
        clean = href.split('?')[0]
        if not clean.lower().endswith(('.xlsx', '.xlsm')):
            continue
        report = _report_for(clean.rsplit('/', 1)[-1])
        url = urljoin(page_url, href)
        if not report or url in seen:
            continue
        seen.add(url)
        try:
            response = client.get(url)
            response.raise_for_status()
            found = _parse_workbook(response.content, report[1])
        except Exception:
            continue
        if found:
            products.extend(found)
            loaded.append(report[0])
    if not products:
        return [], ''
    return products, f'Read {len(loaded)} Ministry of Agriculture price reports ({", ".join(loaded)}).'
