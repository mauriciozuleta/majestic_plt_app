"""
Corabastos' own daily "Boletin Diario de Precios" PDF — NOT the DANE-SIPSA
regional bulletin (that one reports price ranges per package requiring
inferred package weights, which produced unreliable outliers in testing;
kept only as a documented rejection, not used here).

URL pattern confirmed against the live bulletin-calendar widget embedded in
https://corabastos.com.co/boletin-precios-corabastos:
  https://corabastos.com.co/wp-content/uploads/{YYYY}/{MM}/Boletin_diario_{YYYYMMDD}.pdf
Published on business days only — a weekend/holiday date will 404, which
surfaces as a normal per-source fetch failure (no fallback date is guessed).

Each PDF page is one category table, in a fixed order matching the spec's
canonical 10 categories (confirmed by inspecting a real bulletin). If
Corabastos ever reorders the bulletin's pages this mapping needs updating —
there's no category label in the page text itself to detect it from.

`Precio Unidad` is always `Precio Extra / Cantidad`, confirmed across every
sampled row. For KILO (cantidad=1), BULTO (cantidad=25/50/60/70) and TONELADA
(cantidad=1000) rows, that Cantidad is a real kilogram count — a "bulto" is a
standard-weight sack and a "tonelada" is 1000kg by definition, a convention
that holds across every category observed (grains, tubers, fruit, veg) — so
Precio Unidad for those rows already IS a genuine per-kg price. Every other
`Unidad de medida` (ATADO, DOCENA, CAJA, CANASTILLA, BOLSA, PAQUETE, ROLLO,
"N UNIDADES", "N LIBRAS") is a count/bundle unit with no standard kilogram
equivalence and is deliberately left non-comparable.
"""

import re
from datetime import date
from io import BytesIO

import httpx
import pdfplumber

from .match_table import CORABASTOS_TO_LA_MAYORISTA_ID
from .text_normalize import normalize_id

KG_EQUIVALENT_UNITS = {'KILO', 'BULTO', 'TONELADA'}

PAGE_CATEGORY_MAP = {
    1: 'pollo',
    2: 'pescados_mariscos',
    3: 'granos_procesados',
    4: 'platanos',
    5: 'tuberculos',
    6: 'frutas',
    8: 'hortalizas',
    9: 'carnicos',
    10: 'huevos',
    11: 'lacteos',
}


def build_bulletin_url(for_date=None):
    for_date = for_date or date.today()
    return (
        f'https://corabastos.com.co/wp-content/uploads/{for_date.year:04d}/{for_date.month:02d}/'
        f'Boletin_diario_{for_date.strftime("%Y%m%d")}.pdf'
    )


def download_pdf(url):
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    return response.content


def _parse_money(text):
    digits = re.sub(r'[^\d]', '', text or '')
    return float(digits) if digits else None


def parse_pdf(pdf_bytes):
    products = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            category = PAGE_CATEGORY_MAP.get(page_index)
            if not category:
                continue

            for table in page.extract_tables():
                for row in table:
                    cleaned = [cell.strip().replace('\n', ' ') for cell in row if cell and cell.strip()]
                    if len(cleaned) != 8 or cleaned[0] == 'Nombre':
                        continue

                    name, presentacion, cantidad, unidad, _extra, _primera, precio_unidad, _variacion = cleaned
                    if 'IMPORTADO' in name.upper() or 'IMPORTADA' in name.upper():
                        continue

                    price = _parse_money(precio_unidad)
                    if price is None:
                        continue

                    is_kg = unidad.strip().upper() in KG_EQUIVALENT_UNITS
                    raw_id = normalize_id(name)
                    mapped_id = CORABASTOS_TO_LA_MAYORISTA_ID.get(raw_id, raw_id)
                    products.append({
                        'id': normalize_id(mapped_id),
                        'category': category,
                        'nameEs': name.title(),
                        'unit': 'kg' if is_kg else 'other',
                        'unitLabel': None if is_kg else f'{presentacion} ({cantidad} per package)',
                        'price': price,
                    })

    return products


def fetch_corabastos_products():
    url = build_bulletin_url()
    pdf_bytes = download_pdf(url)
    return parse_pdf(pdf_bytes)
