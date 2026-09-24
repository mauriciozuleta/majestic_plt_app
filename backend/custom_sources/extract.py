"""Turns a user-added product source (a website, or an uploaded file) into
the same flat product list the built-in Colombia/USA sources produce:
{id, category, name, unit, price, currency}.

Files (csv / xlsx / pdf) are read deterministically: find the header row that
has a product-name column and a price column, then read the rows under it.

A website is analysed in escalating steps, stopping at the first that yields
products:
  1. the URL itself is a data file (xlsx/csv/pdf) or a Google Sheet
  2. the page links to a data file / Google Sheet (like La Mayorista's
     "Descargar precios") -> download and parse it
  3. the page has an HTML table with product + price columns
  4. Claude reads the page text and pulls out the products (needs the
     API key; this is what handles pages that are prose or unusual markup)
If none work the caller is told to ask the user for a file instead. Nothing
is guessed: a page with no readable prices yields no products.
"""

import csv
import io
import json
import os
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from ..price_sources.text_normalize import normalize_id
from . import moa_jamaica

MAX_PRODUCTS = 3000
MAX_PAGE_TEXT = 40000
USER_AGENT = 'Mozilla/5.0 (compatible; MajesticProductAnalysis/1.0)'
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-5'

FILE_EXTENSIONS = ('.xlsx', '.xlsm', '.xls', '.csv', '.pdf')
SHEET_LINK = re.compile(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)')
# Government market-price bulletins are routinely split across several
# distinct files (one per market, one per report type) rather than one
# canonical sheet — up to this many distinct file links get downloaded and
# combined, not just the first one that works.
MAX_LINKED_FILES = 20

NAME_HEADERS = ('product', 'producto', 'item', 'articulo', 'nombre', 'name', 'description', 'descripcion', 'commodity')
# 'average'/'avg' rank above 'maximo'/'max' — when a table offers both (a
# common Min/Max/Mode/Avg layout), the average is the more representative
# "current price" than the high end of the range.
PRICE_HEADERS = ('price', 'precio', 'average', 'avg', 'promedio', 'cost', 'costo', 'valor', 'value', 'rate', 'maximo', 'max')
UNIT_HEADERS = ('unit', 'unidad', 'uom', 'measure', 'medida', 'per')
CATEGORY_HEADERS = ('category', 'categories', 'categoria', 'categorias', 'group', 'grupo', 'type', 'tipo', 'class', 'clase', 'family', 'familia')
CURRENCY_HEADERS = ('currency', 'moneda')


class SourceError(Exception):
    """A user-presentable reason a source couldn't be read."""


def _plain(text) -> str:
    """Lowercased, accent-stripped, with underscores/hyphens opened into
    spaces — only for matching a header CELL against a candidate header
    word (see _find_columns); product/price/etc. values are never run
    through this. Without the underscore/hyphen split, a machine-generated
    header like "store_product_name" or "store-product-name" never matches
    the "product"/"name" candidates at all: \\b (a word/non-word boundary)
    doesn't fire between two word characters, and '_'/'-' both count as
    word characters to \\w just like a letter does — confirmed while
    debugging a real scraped-catalog file whose header was entirely
    snake_case, which made every column in it undetectable."""
    text = unicodedata.normalize('NFD', str(text or ''))
    plain = ''.join(c for c in text if unicodedata.category(c) != 'Mn').lower().strip()
    return re.sub(r'[_-]+', ' ', plain)


def parse_price(value):
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    text = re.sub(r'[^\d.,-]', '', str(value or ''))
    if not text or not re.search(r'\d', text):
        return None
    if ',' in text and '.' in text:
        decimal = ',' if text.rfind(',') > text.rfind('.') else '.'
        thousands = '.' if decimal == ',' else ','
        text = text.replace(thousands, '').replace(decimal, '.')
    elif ',' in text:
        text = text.replace(',', '.') if re.search(r',\d{1,2}$', text) else text.replace(',', '')
    elif text.count('.') > 1 or re.fullmatch(r'\d{1,3}\.\d{3}', text):
        # 1.234.567 or 8.200 — dots as thousands separators (prices are never quoted to 3 decimals)
        text = text.replace('.', '')
    try:
        price = float(text)
    except ValueError:
        return None
    return price if price >= 0 else None


def _find_columns(header: list) -> dict | None:
    """Column indexes for name/price (required) and unit/category/currency
    (optional), or None if the row doesn't look like a product header."""
    cells = [_plain(cell) for cell in header]

    def find(candidates, exclude=()):
        for candidate in candidates:  # earlier candidates win
            for index, cell in enumerate(cells):
                if index in exclude:
                    continue
                if cell == candidate or re.search(rf'\b{re.escape(candidate)}\b', cell):
                    return index
        return None

    name = find(NAME_HEADERS)
    if name is None:
        return None
    price = find(PRICE_HEADERS, exclude=(name,))
    if price is None:
        return None
    used = {name, price}
    unit = find(UNIT_HEADERS, exclude=used)
    if unit is not None:
        used.add(unit)
    category = find(CATEGORY_HEADERS, exclude=used)
    if category is not None:
        used.add(category)
    currency = find(CURRENCY_HEADERS, exclude=used)
    return {'name': name, 'price': price, 'unit': unit, 'category': category, 'currency': currency}


MAX_SECTION_HEADER_CHARS = 28  # "CONDIMENTS AND SPICES" (21) is a real one; "NATIONAL AGRICULTURAL
                               # MARKETING" (32), a repeated PDF-page letterhead, is not — see below.


def _is_section_header(name: str, cells: list, name_index: int) -> bool:
    """An all-caps row with nothing else filled in ("CITRUS", "FISH", "BEEF
    CUTS") is a category divider, not a product — several government price
    bulletins group commodities this way. A real product row always has a
    price in the price column, so this never misclassifies one: it's only
    ever reached after that row has already failed to parse a price.

    The length cap exists because a multi-page PDF's letterhead/title block
    (page 1's own copy is skipped while still hunting for the header row,
    but a later page's copy arrives after columns are already known, so it
    reaches this check too) can otherwise look exactly like one: short,
    all-caps, nothing else on the row. A real category name is a couple of
    words; an agency's full name usually isn't."""
    if not name or len(name) > MAX_SECTION_HEADER_CHARS or not name.replace(' ', '').isalpha() or name.upper() != name:
        return False
    return not any(str(cell).strip() for index, cell in enumerate(cells) if index != name_index and cell not in (None, ''))


def _rows_to_products(rows: list[list], default_currency: str = '') -> list[dict]:
    """First row that looks like a header defines the columns; everything
    after it that has a name and a numeric price is a product. A section-
    header row (see `_is_section_header`) isn't a product either — it's
    carried forward as every following row's category until the next one."""
    products: list[dict] = []
    columns = None
    width = 0
    section = ''
    for row in rows:
        if columns is None:
            columns = _find_columns(row)
            if columns:
                width = max(index for index in columns.values() if index is not None) + 1
            continue
        cells = list(row) + [''] * (width - len(row))
        name = str(cells[columns['name']] or '').strip()
        price = parse_price(cells[columns['price']])
        if price is None and _is_section_header(name, cells, columns['name']):
            section = name.title()
            continue
        if not name or price is None or len(name) > 120:
            continue
        unit = str(cells[columns['unit']] or '').strip() if columns['unit'] is not None else ''
        category = str(cells[columns['category']] or '').strip() if columns['category'] is not None else ''
        currency = str(cells[columns['currency']] or '').strip() if columns['currency'] is not None else ''
        products.append(
            {
                'id': normalize_id(name),
                'category': section or category or 'Uncategorized',
                'name': name,
                'unit': unit or 'unit',
                'price': price,
                'currency': (currency or default_currency).upper(),
            }
        )
        if len(products) >= MAX_PRODUCTS:
            break
    return products


# ---------------------------------------------------------------- files


def _decode_text(content: bytes) -> str:
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode('utf-8', errors='replace')


def _parse_csv(content: bytes) -> list[dict]:
    text = _decode_text(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
    return _rows_to_products(list(csv.reader(io.StringIO(text), dialect)))


def _parse_xlsx(content: bytes) -> list[dict]:
    import openpyxl

    from ..price_sources.la_mayorista import _strip_defined_names

    workbook = openpyxl.load_workbook(_strip_defined_names(content), data_only=True, read_only=True)
    try:
        for sheet in workbook.worksheets:
            products = _rows_to_products([list(row) for row in sheet.iter_rows(values_only=True)])
            if products:
                return products
    finally:
        workbook.close()
    return []


def _parse_xls(content: bytes) -> list[dict]:
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    for sheet in book.sheets():
        products = _rows_to_products([sheet.row_values(index) for index in range(sheet.nrows)])
        if products:
            return products
    return []


def _parse_pdf(content: bytes) -> list[dict]:
    import pdfplumber

    # One flat row stream for the whole document, not one attempt per table:
    # pdfplumber often detects a title/header block and the data underneath
    # it as two separate "tables" on the same page (a merged title cell
    # breaks the grid it's tracking), which left the header with no rows to
    # apply to and the data with no header to find — nothing ever parsed.
    # Concatenating first, and only then reading the whole thing as one
    # table, header included, fixes that regardless of how pdfplumber chose
    # to split it up. A page's title/repeated-header rows reappearing later
    # in the stream are harmless: they have no valid price, so they're
    # dropped by the same rule that skips any other non-product row.
    rows: list[list] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                rows.extend([cell or '' for cell in row] for row in table)
    return _rows_to_products(rows)


def parse_file(filename: str, content: bytes) -> list[dict]:
    """Products from an uploaded file. Raises SourceError with a message fit
    to show a user."""
    extension = os.path.splitext(filename.lower())[1]
    if extension not in FILE_EXTENSIONS:
        raise SourceError(f'"{extension or "this file type"}" is not supported — use ' + ', '.join(FILE_EXTENSIONS) + '.')
    try:
        if extension == '.csv':
            products = _parse_csv(content)
        elif extension == '.pdf':
            products = _parse_pdf(content)
        elif extension == '.xls':
            products = _parse_xls(content)
        else:
            products = _parse_xlsx(content)
    except SourceError:
        raise
    except Exception as error:
        raise SourceError(f'Could not read this file: {error}') from error
    if not products:
        raise SourceError(
            'No products were found. The file needs a header row with at least a product name column and a price '
            'column (for example: Product, Category, Unit, Price).'
        )
    return products


# ---------------------------------------------------------------- website


class _PageParser(HTMLParser):
    """Collects the visible text, the links, and every table's rows."""

    _SKIP = {'script', 'style', 'noscript', 'svg', 'head'}

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.links: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._skip_depth = 0
        self._table_stack: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)
        elif tag == 'table':
            self._table_stack.append([])
        elif tag == 'tr' and self._table_stack:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r'\s+', ' ', ''.join(self._cell)).strip())
            self._cell = None
        elif tag == 'tr' and self._row is not None and self._table_stack:
            if any(self._row):
                self._table_stack[-1].append(self._row)
            self._row = None
        elif tag == 'table' and self._table_stack:
            self.tables.append(self._table_stack.pop())

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        if data.strip():
            self.text.append(data.strip())


def _claude_key():
    return os.environ.get('CLAUDE_API_KEY') or os.environ.get('claude_api_key')


def _claude_extract(url: str, page_text: str) -> list[dict]:
    api_key = _claude_key()
    if not api_key:
        return []
    prompt = f"""This is the text of a web page ({url}) that may list wholesale or market prices for food / \
agricultural products. Extract every product that has a price on the page.

Return ONLY a JSON array (no prose, no code fence). Each element: \
{{"name": string, "category": string, "unit": string, "price": number, "currency": string}}.
- name: the product as written (keep the original language).
- category: a short category if the page groups products (e.g. Fruits, Vegetables, Meat), else "".
- unit: what the price is per (kg, lb, dozen, unit, ...), else "".
- price: a plain number — never a range, use the higher figure if a range is shown.
- currency: ISO code if stated or clearly implied (USD, COP, EUR...), else "".
If the page contains no product prices, return [].

Page text:
{page_text[:MAX_PAGE_TEXT]}"""
    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={'x-api-key': api_key, 'anthropic-version': ANTHROPIC_VERSION, 'content-type': 'application/json'},
            json={'model': MODEL, 'max_tokens': 16000, 'messages': [{'role': 'user', 'content': prompt}]},
            timeout=180,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    text = ''.join(block.get('text', '') for block in response.json().get('content', []) if block.get('type') == 'text')
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []
    try:
        rows = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    products = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip()
        price = parse_price(row.get('price'))
        if not name or price is None:
            continue
        products.append(
            {
                'id': normalize_id(name),
                'category': str(row.get('category') or '').strip() or 'Uncategorized',
                'name': name,
                'unit': str(row.get('unit') or '').strip() or 'unit',
                'price': price,
                'currency': str(row.get('currency') or '').strip().upper(),
            }
        )
        if len(products) >= MAX_PRODUCTS:
            break
    return products


def _ssl_context():
    """Trust the operating system's certificate store rather than Python's
    bundled list. Some government sites (moa.gov.jm, for one) serve an
    incomplete certificate chain that browsers and Windows repair by fetching
    the missing intermediate, but Python's own verification rejects."""
    try:
        import ssl

        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return True


def _download(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _products_from_response(filename_hint: str, response: httpx.Response) -> list[dict]:
    content_type = response.headers.get('content-type', '').lower()
    name = filename_hint.lower()
    if 'pdf' in content_type or name.endswith('.pdf'):
        return _parse_pdf(response.content)
    if 'csv' in content_type or name.endswith('.csv'):
        return _parse_csv(response.content)
    if name.endswith('.xls'):
        return _parse_xls(response.content)
    if 'spreadsheet' in content_type or 'excel' in content_type or name.endswith(('.xlsx', '.xlsm')):
        return _parse_xlsx(response.content)
    return []


def analyze_url(url: str) -> tuple[list[dict], str]:
    """(products, note about how they were found). Raises SourceError with a
    reason a user can act on when nothing could be extracted."""
    if not re.match(r'^https?://', url, re.IGNORECASE):
        raise SourceError('The address must start with http:// or https://.')

    try:
        with httpx.Client(
            timeout=40, follow_redirects=True, headers={'User-Agent': USER_AGENT}, verify=_ssl_context()
        ) as client:
            page = _download(client, url)

            # 1. The URL is itself a data file.
            products = _safe(lambda: _products_from_response(str(page.url).split('?')[0], page))
            if products:
                return products, 'Read directly from the file at this address.'

            content_type = page.headers.get('content-type', '').lower()
            if 'html' not in content_type and 'text' not in content_type:
                raise SourceError('This address is not a web page or a readable price file (xlsx, csv, pdf).')

            parser = _PageParser()
            parser.feed(page.text)

            # Sites with a dedicated reader (their files need site-specific parsing).
            if moa_jamaica.matches(url):
                products, note = moa_jamaica.analyze(client, str(page.url), parser.links)
                if products:
                    return products, note

            # 2. The page links to one or more price files / Google Sheets.
            # A government price bulletin routinely splits its current data
            # across several files (one per market, one per report) rather
            # than a single canonical sheet, so every distinct file that
            # actually parses gets combined — not just whichever is first in
            # the page's HTML (which needn't even be the right one; the very
            # first PDF link on a page is often something unrelated, like a
            # citizen's charter).
            candidates: list[tuple[str, str]] = []
            seen_urls = set()
            for href in parser.links:
                sheet = SHEET_LINK.search(href)
                file_url, hint = (
                    (f'https://docs.google.com/spreadsheets/d/{sheet.group(1)}/export?format=xlsx', 'sheet.xlsx')
                    if sheet
                    else (urljoin(str(page.url), href), href.split('?')[0])
                )
                if not sheet and not href.lower().split('?')[0].endswith(FILE_EXTENSIONS):
                    continue
                if file_url in seen_urls:
                    continue
                seen_urls.add(file_url)
                candidates.append((file_url, hint))

            products, read_files = [], []
            for file_url, hint in candidates[:MAX_LINKED_FILES]:
                found = _safe(lambda: _products_from_response(hint, _download(client, file_url)))
                if found:
                    products.extend(found)
                    read_files.append(hint.rsplit('/', 1)[-1])
            if products:
                names = ', '.join(read_files[:5]) + ('…' if len(read_files) > 5 else '')
                plural = 'file' if len(read_files) == 1 else f'{len(read_files)} files'
                return products, f'Read from the price {plural} this page links to ({names}).'

            # 3. An HTML table with product + price columns.
            for table in parser.tables:
                products = _rows_to_products(table)
                if len(products) >= 3:
                    return products, 'Read from a price table on the page.'

            # 4. Let Claude read the page text.
            page_text = '\n'.join(parser.text)
            if len(page_text) > 200:
                products = _claude_extract(str(page.url), page_text)
                if products:
                    return products, 'Extracted from the page text with AI — worth a quick check.'
    except httpx.HTTPStatusError as error:
        raise SourceError(f'The site answered with an error ({error.response.status_code}).') from error
    except httpx.HTTPError as error:
        raise SourceError(f'Could not reach the site: {error}') from error

    raise SourceError("No product prices could be found on this site (it may load them with JavaScript or behind a login).")


def _safe(action):
    try:
        return action()
    except Exception:
        return []

