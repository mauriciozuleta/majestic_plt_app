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

Farmgate and Rural Municipal stack several tables down one sheet, each with
its own "Commodity" header row naming the next two parishes/markets
(Manchester & St. Andrew, then St. Catherine & Clarendon, ...) and repeating
the whole commodity list. Every table is read, and a commodity's blocks from
all of them are merged into ONE product per report — not one per table.

Each row is a commodity with a "Variety/Source" (Local / Imported / a brand),
which is kept in the product name — "Broccoli (Imported)" and "Broccoli
(Local)" are different products with different prices. For the per-market
reports the price is the average of the markets' "Most Frequent" prices, with
the lowest Low and highest High across them kept as a range. Unit and
currency come from each sheet's own title ("Retail Prices (J$/Kg)"). Each per-market product keeps
`market_prices` — every parish/market's own Most Frequent price — so the
average can be checked.

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


def _product(commodity, variety, category, unit, currency, week, price, low=None, high=None, markets=None, market_prices=None) -> dict:
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
    if market_prices:
        product['market_prices'] = market_prices
    return product


def _layout(rows: list[list], header_at: int) -> dict:
    """Column layout of the table whose "Commodity" header row is `header_at`:
    the per-market blocks (each block's Most Frequent column and the market
    named above it), or the single price column of a flat report."""
    raw_header = list(rows[header_at])
    header = [_text(cell).lower() for cell in raw_header]
    sub = [_text(cell).lower() for cell in (rows[header_at + 1] if header_at + 1 < len(rows) else [])]
    # Columns whose sub-header says "most frequent" mark one market/parish block each;
    # the market's name sits above the block's first (Low) column.
    frequent = [i for i, cell in enumerate(sub) if 'frequent' in cell and i >= 2]
    markets = {i: _text(raw_header[i - 2]) if i - 2 < len(raw_header) else '' for i in frequent}
    flat_price = next((i for i, cell in enumerate(header) if 'most frequent' in cell), None)
    if flat_price is None:
        flat_price = next((i for i, cell in enumerate(header) if 'average' in cell), None)
    return {'header': header, 'frequent': frequent, 'markets': markets, 'flat_price': flat_price}


def _parse_sheet(rows: list[list], category: str) -> list[dict]:
    header_at = _find_header(rows)
    if header_at is None:
        return []
    currency, unit, week = _sheet_info(rows)
    layout = _layout(rows, header_at)

    # (commodity, variety, category) -> merged blocks / flat price, in first-seen order
    merged: dict[tuple, dict] = {}
    section = ''

    # Rows under a header that aren't products (a Low/High sub-header, the
    # retail store-name row) have no numeric price and fall out below.
    for index in range(header_at + 1, len(rows)):
        row = rows[index]
        commodity = _text(row[0] if row else '')
        if commodity.lower() == 'commodity':
            # The next stacked table (Farmgate / Rural Municipal): new markets.
            layout = _layout(rows, index)
            section = ''
            continue
        frequent, flat_price = layout['frequent'], layout['flat_price']
        cells = list(row) + [None] * max(0, (max(frequent) if frequent else (flat_price or 0)) + 1 - len(row))
        variety = _text(cells[1]) if len(cells) > 1 else ''
        if not commodity:
            continue
        others = [c for c in cells[1:] if c not in (None, '')]
        if not others and commodity.isupper():
            section = commodity.title()  # e.g. "BEEF CUTS" in the meat sheet
            continue

        cat = f'{category} — {section}' if section else category
        key = (commodity, variety, cat)
        if frequent:
            # Per-market blocks: Low is two columns before Most Frequent, High one before.
            entry = merged.setdefault(key, {'blocks': []})
            for i in frequent:
                price = _number(cells[i])
                if price is None:
                    continue
                entry['blocks'].append(
                    {
                        'market': layout['markets'].get(i) or f'Market {len(entry["blocks"]) + 1}',
                        'price': price,
                        'low': _number(cells[i - 2]) if i - 2 >= 2 else None,
                        'high': _number(cells[i - 1]) if i - 1 >= 2 else None,
                    }
                )
        elif flat_price is not None and key not in merged:
            price = _number(cells[flat_price])
            if price is None:
                continue
            low = high = None
            if 'most frequent' in layout['header'][flat_price]:  # Wholesale: has Lowest / Highest beside it
                low = _number(cells[flat_price - 2]) if flat_price >= 2 else None
                high = _number(cells[flat_price - 1]) if flat_price >= 1 else None
            merged[key] = {'flat': _product(commodity, variety, cat, unit, currency, week, price, low=low, high=high)}

    products: list[dict] = []
    for (commodity, variety, cat), entry in merged.items():
        if 'flat' in entry:
            products.append(entry['flat'])
            continue
        blocks = entry['blocks']
        if not blocks:
            continue  # no market had a price this week
        lows = [block['low'] for block in blocks if block['low'] is not None]
        highs = [block['high'] for block in blocks if block['high'] is not None]
        products.append(
            _product(
                commodity, variety, cat, unit, currency, week,
                round(sum(block['price'] for block in blocks) / len(blocks), 2),
                low=min(lows) if lows else None,
                high=max(highs) if highs else None,
                markets=len(blocks),
                market_prices=[{'market': block['market'], 'price': block['price']} for block in blocks],
            )
        )
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
