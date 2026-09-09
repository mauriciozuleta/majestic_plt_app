"""
La Mayorista (Central Mayorista de Antioquia) price sheet: resolve the
current Google Sheets file ID from the homepage's "Descargar precios" link
(never hardcode it — the linked file can be replaced), download it as xlsx,
and parse the five stacked category blocks.

Price selection rule (per spec): today's Maximo, for both sources, so the
comparison isn't skewed by one source using an average and the other a
range extreme.
"""

import io
import re
import zipfile

import httpx
import openpyxl

from .category_refine import refine_carnicos_lacteos_block, refine_hortalizas_block
from .text_normalize import normalize_id

HOMEPAGE_URL = 'https://lamayorista.com.co/'
SHEET_URL_PATTERN = re.compile(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)')

# Row-1 category label -> canonical category (None = exclude entirely)
CATEGORY_BLOCKS = {
    'VERDURAS Y HORTALIZAS': 'hortalizas',
    'FRUTAS': 'frutas',
    'PROCESADOS Y GRANOS': 'granos_procesados',
    'CÁRNICOS Y LÁCTEOS': 'carnicos_lacteos',  # refined per-item below
    'FRUTAS IMPORTADAS': None,  # imported goods, not local wholesale comparables
}

# A parenthetical/bare unit mention that means this row's price is NOT a
# plain per-kg figure (a package, bottle, or a non-kg weight unit).
_BARE_UNIT_PATTERN = re.compile(r'(\d+\s*(?:cm3|ml|gramos?))', re.IGNORECASE)
_NON_KG_WORDS = ('libra', 'arroba', 'gramo')


def _extract_unit_note(name):
    """Returns None if the row is safely per-kg, otherwise a short label for
    the actual (non-kg) unit this price is quoted in."""
    match = re.search(r'\(([^)]*)\)', name)
    if match:
        inner = match.group(1).strip()
        lower = inner.lower()
        if lower in ('kilo', 'kilos'):
            return None
        if re.search(r'\d', inner) or any(word in lower for word in _NON_KG_WORDS):
            return inner
        return None
    bare = _BARE_UNIT_PATTERN.search(name)
    if bare:
        return bare.group(1)
    # e.g. "Huevo AA unidad" — priced per single egg, not per kg.
    if re.search(r'\bunidad\b', name, re.IGNORECASE):
        return 'unidad'
    return None


def resolve_sheet_id():
    response = httpx.get(HOMEPAGE_URL, timeout=15, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    match = SHEET_URL_PATTERN.search(response.text)
    if not match:
        raise RuntimeError('Could not find the "Descargar precios" Google Sheets link on the La Mayorista homepage.')
    return match.group(1)


def _strip_defined_names(xlsx_bytes):
    """Google's xlsx export embeds chart-sheet defined names that a known
    openpyxl bug chokes on (AttributeError on Chartsheet.defined_names).
    Stripping the <definedNames> block from workbook.xml sidesteps it —
    we only need the data sheet, not the chart sheets."""
    buffer_in = io.BytesIO(xlsx_bytes)
    buffer_out = io.BytesIO()
    with zipfile.ZipFile(buffer_in, 'r') as zin, zipfile.ZipFile(buffer_out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'xl/workbook.xml':
                data = re.sub(rb'<definedNames>.*?</definedNames>', b'', data, flags=re.DOTALL)
            zout.writestr(item, data)
    buffer_out.seek(0)
    return buffer_out


def fetch_workbook_bytes(sheet_id):
    export_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
    response = httpx.get(export_url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.content


def parse_workbook(xlsx_bytes):
    workbook = openpyxl.load_workbook(_strip_defined_names(xlsx_bytes), data_only=True)
    sheet = workbook['Hoja1']

    products = []
    current_category = None
    skip_category = False

    for row in sheet.iter_rows(values_only=True):
        name_cell = row[1] if len(row) > 1 else None
        col_c = row[2] if len(row) > 2 else None

        if isinstance(name_cell, str) and name_cell.strip() in CATEGORY_BLOCKS:
            mapped = CATEGORY_BLOCKS[name_cell.strip()]
            current_category = mapped
            skip_category = mapped is None
            continue

        if skip_category or current_category is None:
            continue
        if not isinstance(name_cell, str) or not isinstance(col_c, (int, float)):
            continue  # date row, blank row, or anything that isn't a product row

        name = name_cell.strip()
        today_max = row[6] if len(row) > 6 else None
        if not isinstance(today_max, (int, float)):
            continue

        if current_category == 'hortalizas':
            category = refine_hortalizas_block(name)
        elif current_category == 'carnicos_lacteos':
            category = refine_carnicos_lacteos_block(name)
        else:
            category = current_category

        unit_note = _extract_unit_note(name)
        products.append({
            'id': normalize_id(name),
            'category': category,
            'nameEs': name,
            'unit': 'other' if unit_note else 'kg',
            'unitLabel': unit_note,
            'price': float(today_max),
        })

    return products


def fetch_la_mayorista_products():
    sheet_id = resolve_sheet_id()
    workbook_bytes = fetch_workbook_bytes(sheet_id)
    return parse_workbook(workbook_bytes)
