"""United States: import duty from the Harmonized Tariff Schedule (USITC export, hts_full.json) plus the customs user fees.

The HTS lists per line a General rate (MFN), a Special rate with the trade programs that qualify for it ("Free (AU,BH,CO,E,…)"), and a
column-2 rate (for Cuba, North Korea, Russia, Belarus). Rates are ad valorem (6.4%), specific (3.9¢/kg, $1.20/doz) or both
("2.5¢/kg + 5%"). The customs value in the US is the transaction value, so freight and insurance are NOT in the duty base.

What is NOT computed (reported on every result): Section 232 / 301 / IEEPA ("reciprocal") duties and anti-dumping or countervailing
duties — they sit in HTS chapter 99 or in separate orders and change often — and informal-entry fees for shipments of USD 2,500 or less.
"""

import json
import re
import urllib.request
from datetime import datetime

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank

FOLDER = DATA_ROOT / 'United States'
URL = 'https://hts.usitc.gov/reststop/exportList?from=0101&to=9999&format=JSON&styles=false'

# HTS special-program code -> origin countries that qualify (a curated list; the code shown in the result says which one applied)
PROGRAMS = {
    'AU': ['Australia'], 'BH': ['Bahrain'], 'CL': ['Chile'], 'CO': ['Colombia'], 'IL': ['Israel'], 'JO': ['Jordan'],
    'KR': ['South Korea', 'Korea, Republic of', 'Korea'], 'MA': ['Morocco'], 'OM': ['Oman'], 'PA': ['Panama'], 'PE': ['Peru'], 'SG': ['Singapore'],
    'CA': ['Canada'], 'MX': ['Mexico'], 'S': ['Canada', 'Mexico'],  # USMCA
    'P': ['Costa Rica', 'Dominican Republic', 'El Salvador', 'Guatemala', 'Honduras', 'Nicaragua'],  # CAFTA-DR
    'E': ['Antigua and Barbuda', 'Bahamas', 'Barbados', 'Belize', 'Dominica', 'Grenada', 'Guyana', 'Haiti', 'Jamaica', 'Montserrat', 'Saint Kitts and Nevis',
          'Saint Lucia', 'Saint Vincent and the Grenadines', 'Trinidad and Tobago', 'Panama', 'Costa Rica', 'El Salvador', 'Guatemala', 'Honduras', 'Nicaragua'],  # CBERA
}
PROGRAM_NAMES = {
    'CO': 'US-Colombia Trade Promotion Agreement', 'E': 'Caribbean Basin Economic Recovery Act (CBERA)', 'S': 'USMCA', 'CA': 'USMCA/NAFTA', 'MX': 'USMCA/NAFTA',
    'P': 'CAFTA-DR', 'AU': 'US-Australia FTA', 'BH': 'US-Bahrain FTA', 'CL': 'US-Chile FTA', 'IL': 'US-Israel FTA', 'JO': 'US-Jordan FTA',
    'KR': 'US-Korea FTA', 'MA': 'US-Morocco FTA', 'OM': 'US-Oman FTA', 'PA': 'US-Panama TPA', 'PE': 'US-Peru TPA', 'SG': 'US-Singapore FTA',
}
COLUMN_2 = {'cuba', 'north korea', 'korea, democratic people\'s republic of', 'russia', 'russian federation', 'belarus'}

# Customs user fees (statutory figures for fiscal year 2026 — verify against CBP when the year changes)
MPF = {'rate': 0.003464, 'minimum': 33.58, 'maximum': 651.50, 'as_of': 'FY2026 (Oct 2025–Sep 2026)'}
HMF_RATE = 0.00125  # harbor maintenance fee, ocean shipments only
FORMAL_ENTRY_MINIMUM = 2500.0

KG_UNITS = {'kg'}


def _rate_parts(text: str) -> tuple[list[dict], bool]:
    """A rate as written -> components [{'type': 'adv', 'pct'} | {'type': 'spec', 'usd', 'per'}], and whether all of it was understood."""
    text = (text or '').replace('¢', 'c').replace('�', 'c').strip()
    if not text or text.lower() == 'free':
        return [], True
    parts, understood = [], True
    for piece in re.split(r'\s\+\s', text):
        piece = piece.strip()
        match = re.fullmatch(r'(\d+(?:\.\d+)?)%', piece)
        if match:
            parts.append({'type': 'adv', 'pct': float(match.group(1))})
            continue
        match = re.fullmatch(r'(\d+(?:\.\d+)?)c/([A-Za-z0-9.]+)', piece)
        if match:
            parts.append({'type': 'spec', 'usd': float(match.group(1)) / 100, 'per': match.group(2).lower().rstrip('.')})
            continue
        match = re.fullmatch(r'\$(\d+(?:\.\d+)?)/([A-Za-z0-9.]+)', piece)
        if match:
            parts.append({'type': 'spec', 'usd': float(match.group(1)), 'per': match.group(2).lower().rstrip('.')})
            continue
        understood = False
    return parts, understood


def _segments(special: str) -> list[tuple[str, set[str]]]:
    """'Free (AU,BH,CO,E) 1.2% (X)' -> [('Free', {'AU','BH','CO','E'}), ('1.2%', {'X'})]"""
    out = []
    for rate, codes in re.findall(r'([^()]+?)\s*\(([^)]*)\)', special or ''):
        out.append((rate.strip(), {code.strip().rstrip('+*') for code in re.split(r'[,\s]+', codes) if code.strip()}))
    return out


class UsaCalculator(Calculator):
    name = 'United States'
    currency = 'USD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.loaded_at: str | None = None

    @property
    def path(self):
        return FOLDER / 'hts_full.json'

    # ------------------------------------------------------------ data
    def refresh(self) -> dict:
        """Downloads the current HTS from the USITC and reloads it."""
        FOLDER.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with urllib.request.urlopen(URL, timeout=300) as response, open(temp, 'wb') as handle:
            handle.write(response.read())
        json.loads(temp.read_text(encoding='utf-8'))  # must be valid before it replaces the working copy
        temp.replace(self.path)
        self._load()
        return self.info()

    def _load(self) -> None:
        self.lines, self.by_code = [], {}
        if not self.path.exists():
            return
        rows = json.loads(self.path.read_text(encoding='utf-8'))
        stack: list[dict] = []
        for row in rows:
            indent = int(row.get('indent') or 0)
            while stack and stack[-1]['indent'] >= indent:
                stack.pop()
            description = (row.get('description') or '').strip()
            entry = {'indent': indent, 'description': description, 'line': None}
            general = (row.get('general') or '').strip()
            code = row.get('htsno') or ''
            units = row.get('units') or []
            if general and code:
                path = [item['description'].rstrip(':').strip() for item in stack] + [description.rstrip(':').strip()]
                line = {
                    'code': code,
                    'description': description,
                    'path': ' > '.join(part for part in path if part),
                    'units': units[0] if units else None,
                    'general': general,
                    'special': (row.get('special') or '').strip(),
                    'other': (row.get('other') or '').strip(),
                    'additional': (row.get('additionalDuties') or row.get('addiitionalDuties') or '') or None,
                }
                entry['line'] = line
                self.lines.append(line)
                self.by_code[digits(code)] = line
                self.by_code[code] = line
            elif units:  # a statistical-suffix row below a rate line: it carries the unit of quantity
                for ancestor in reversed(stack):
                    if ancestor['line'] is not None:
                        ancestor['line']['units'] = ancestor['line']['units'] or units[0]
                        break
            stack.append(entry)
        self.loaded_at = datetime.fromtimestamp(self.path.stat().st_mtime).strftime('%Y-%m-%d')

    def _ensure(self) -> None:
        if not self.lines:
            self._load()

    def info(self) -> dict:
        self._ensure()
        return {
            'country': self.name,
            'ready': bool(self.lines),
            'lines': len(self.lines),
            'source': 'USITC Harmonized Tariff Schedule (hts.usitc.gov export)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Downloads the current schedule from hts.usitc.gov (about 12 MB).',
            'currency': self.currency,
        }

    def signature(self, line: dict):
        return (line['general'], line['special'], line['other'])

    # ------------------------------------------------------------ lookup
    def _public(self, line: dict) -> dict:
        return {
            'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['units'],
            'summary': f"General {line['general']}" + (f" · Special {line['special'][:90]}" if line['special'] else ''),
        }

    def search(self, query: str, limit: int = 30) -> list[dict]:
        self._ensure()
        query = (query or '').strip()
        if not query:
            return []
        if re.fullmatch(r'[\d.\s]+', query):
            prefix = digits(query)
            return [self._public(line) for line in self.lines if digits(line['code']).startswith(prefix)][:limit]
        words = query_words(query)
        if not words:
            return []
        scored = []
        for line in self.lines:
            key = rank(line, words)
            if key is not None:
                scored.append((key, line))
        scored.sort(key=lambda item: item[0])
        return [self._public(line) for _, line in scored[:limit]]

    def get(self, code: str) -> dict | None:
        self._ensure()
        line = self.by_code.get(code) or self.by_code.get(digits(code))
        return self._public(line) if line else None

    # ------------------------------------------------------------ calculation
    def _pick_rate(self, line: dict, origin: str | None) -> tuple[str, str, str]:
        """(rate text, column, why) for the origin: a special program it qualifies for, else column 2, else general (MFN)."""
        name = (origin or '').strip().lower()
        if name in COLUMN_2 and line['other']:
            return line['other'], 'Column 2', f'{origin} is subject to the column 2 rate'
        for rate, codes in _segments(line['special']):
            for code in sorted(codes):
                if code in PROGRAMS and any(name == country.lower() for country in PROGRAMS[code]):
                    return rate, f'Special ({code})', f"{origin} qualifies under {PROGRAM_NAMES.get(code, 'program ' + code)} (code {code})"
        why = 'General (MFN) rate' + (f' — no special program in this line applies to {origin}' if origin else '')
        return line['general'], 'General', why

    def calculate(self, code: str, inputs: Inputs) -> Result:
        self._ensure()
        line = self.by_code.get(code) or self.by_code.get(digits(code))
        if line is None:
            raise ValueError(f'HTS line {code} not found (use the 8-digit rate line, for example 0702.00.20).')
        value = inputs.goods_value_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'Customs value (transaction value)', 'amount_usd': round(value, 2), 'formula': f'goods {money(value)} (freight and insurance are not part of the US customs value)'},
            sources=[f"USITC Harmonized Tariff Schedule, line {line['code']}"],
        )
        rate_text, column, why = self._pick_rate(line, inputs.origin)
        result.notes.append(f'{why}: {rate_text}.')
        parts, understood = _rate_parts(rate_text)
        if not understood:
            result.complete = False
            result.warnings.append(f'The duty rate "{rate_text}" has a form this calculator does not read; the duty is not included in the total.')
        elif not parts:
            result.taxes.append(Tax('Customs duty', 0.0, 'Free', 'customs value', f'{column}: free of duty'))
        for part in parts:
            if part['type'] == 'adv':
                result.taxes.append(Tax('Customs duty (ad valorem)', value * part['pct'] / 100, f"{part['pct']:g}%", 'customs value', f"{money(value)} × {part['pct']:g}%"))
                continue
            per = part['per']
            quantity = inputs.quantity_kg if per in KG_UNITS else inputs.quantity_units
            label = f"{part['usd'] * (100 if part['usd'] < 1 else 1):g}{'¢' if part['usd'] < 1 else '$'}/{per}"
            if quantity is None:
                result.complete = False
                result.warnings.append(f'The duty is {label}: enter the quantity in {per} to include it in the total.')
                continue
            result.taxes.append(Tax('Customs duty (specific)', quantity * part['usd'], label, f'{per}', f"{quantity:g} {per} × USD {part['usd']:.4f}"))
        if line['additional']:
            result.warnings.append(f"HTS note on additional duties for this line: {line['additional']}")

        # user fees
        if value > FORMAL_ENTRY_MINIMUM:
            mpf = min(max(value * MPF['rate'], MPF['minimum']), MPF['maximum'])
            result.taxes.append(Tax('Merchandise processing fee (MPF)', mpf, '0.3464%', 'customs value', f"{money(value)} × 0.3464%, minimum {MPF['minimum']}, maximum {MPF['maximum']}", note=f"{MPF['as_of']} amounts"))
        else:
            result.notes.append(f'Shipments of USD {FORMAL_ENTRY_MINIMUM:,.0f} or less may clear as informal entries with different flat fees; no merchandise processing fee is added here.')
        if inputs.transport == 'sea':
            result.taxes.append(Tax('Harbor maintenance fee (HMF)', value * HMF_RATE, '0.125%', 'customs value', f'{money(value)} × 0.125% (ocean shipments)'))
        result.notes.append('The US has no federal VAT or sales tax at import.')
        result.warnings.append('Not included: Section 232, Section 301 and IEEPA ("reciprocal") duties, anti-dumping and countervailing duties — they change often; check the current HTS chapter 99 and CBP guidance for this product and origin.')
        result.warnings.append(f"Customs user fees are the {MPF['as_of']} statutory amounts; verify them when the fiscal year changes.")
        return result
