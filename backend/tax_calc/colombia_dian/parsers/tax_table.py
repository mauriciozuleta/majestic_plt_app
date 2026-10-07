"""The Gravamen / IVA popup tables, from an HTML string (so the parsers run offline against fixtures).

Gravamen columns: `Concepto | Tarifa - Fórmula | Desde | Hasta | Leg`. IVA: `Tarifa - Fórmula | Desde | Hasta | Leg`, or — when the rate
depends on the product — `Nombre del producto | Tarifa - Fórmula | Desde | Hasta | Leg`."""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ..dian_types import TaxValue
from .dates_numbers import fold, is_empty_marker, normalize_text, parse_date, parse_number

LEGAL_ICON_HINT = 'botbaselegal'

_PERCENT = re.compile(r'^\s*(\d[\d.,]*)\s*%\s*(?:[-–]\s*([A-Za-zÁÉÍÓÚáéíóúñÑ ]+?))?\s*$')


@dataclass
class TaxTable:
    found: bool = False
    label_header: str | None = None  # 'Concepto' | 'Nombre del producto' | None (the simple IVA table has no label column)
    rows: list[TaxValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # parse warnings (ambiguous numbers, unreadable dates…)


def classify_formula(raw: str) -> tuple[float | None, str | None, str | None, list[str]]:
    """The 'Tarifa - Fórmula' text -> (rate, unit, classification, warnings). Only a plain percentage becomes a rate: a specific,
    per-kg, mixed or unrecognised formula keeps rate=None."""
    text = normalize_text(raw)
    match = _PERCENT.match(text)
    if match:
        rate, warnings = parse_number(match.group(1))
        tag = fold(match.group(2) or '')
        classification = 'excluded' if 'excluid' in tag else 'exempt' if 'exent' in tag else None
        if rate is None:
            return None, 'formula', classification, warnings
        return rate, 'percent', classification, warnings
    upper = fold(text)
    has_percent = '%' in text
    per_kg = bool(re.search(r'\bkg\b|kilo', upper))
    money = bool(re.search(r'\$|usd|us\$|dolar', upper))
    if has_percent and (money or per_kg or '+' in text):
        return None, 'mixed', None, []
    if per_kg:
        return None, 'specific_per_kg', None, []
    if money:
        return None, 'specific', None, []
    return None, 'formula', None, []


def _cell_text(cell) -> str:
    return normalize_text(cell.get_text(' '))


def own_rows(table) -> list:
    """The rows that belong to this table itself — WebArancel nests the data table inside layout tables, so a plain find_all would also
    return the rows (and headers) of the tables around and inside it."""
    return [tr for tr in table.find_all('tr') if tr.find_parent('table') is table]


def parse_tax_table(html: str) -> TaxTable:
    """Parses the first table whose own header has a 'Tarifa - Fórmula' column. `found=False` when there is none."""
    soup = BeautifulSoup(html, 'html.parser')
    for table in soup.find_all('table'):
        rows = own_rows(table)
        header_row = next((tr for tr in rows if tr.find_all('th', recursive=False)), None)
        if header_row is None:
            continue
        headers = [_cell_text(th) for th in header_row.find_all('th', recursive=False)]
        folded = [fold(header) for header in headers]
        rate_col = next((i for i, header in enumerate(folded) if header.startswith('tarifa')), None)
        if rate_col is None:
            continue
        label_col = next((i for i, header in enumerate(folded) if header in ('concepto', 'nombre del producto')), None)
        from_col = next((i for i, header in enumerate(folded) if header == 'desde'), None)
        to_col = next((i for i, header in enumerate(folded) if header == 'hasta'), None)
        result = TaxTable(found=True, label_header=headers[label_col] if label_col is not None else None)
        for tr in rows:
            cells = tr.find_all('td', recursive=False)
            if len(cells) <= rate_col:
                continue
            raw = _cell_text(cells[rate_col])
            if not raw:
                continue
            rate, unit, classification, warnings = classify_formula(raw)
            result.warnings.extend(warnings)
            dates = []
            for col in (from_col, to_col):
                text = _cell_text(cells[col]) if col is not None and col < len(cells) else ''
                try:
                    dates.append(parse_date(text))
                except ValueError:
                    dates.append(None)
                    result.warnings.append(f'Unreadable date "{text}" in "{raw}".')
            if unit == 'formula' and not is_empty_marker(raw):
                result.warnings.append(f'Unrecognised formula "{raw}": kept as text, no rate.')
            legal = any(LEGAL_ICON_HINT in (img.get('src') or '') for img in tr.find_all('img'))
            result.rows.append(
                TaxValue(
                    rate=rate,
                    unit=unit,
                    formulaRaw=raw,
                    validFrom=dates[0],
                    validTo=dates[1],
                    rawText=normalize_text(tr.get_text(' ')),
                    concept=_cell_text(cells[label_col]) if label_col is not None and label_col < len(cells) else None,
                    classification=classification,
                    hasLegalBasis=legal,
                )
            )
        return result
    return TaxTable(found=False)


def is_valid_on(value: TaxValue, iso_date: str) -> bool:
    """A row applies on a date when validFrom <= date and (validTo is open or >= date). ISO dates compare as text."""
    return (value.validFrom is None or value.validFrom <= iso_date) and (value.validTo is None or value.validTo >= iso_date)
