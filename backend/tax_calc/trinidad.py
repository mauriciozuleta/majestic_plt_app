"""Trinidad and Tobago: import duty from the CARICOM Common External Tariff (Legal Notice No. 218 of 2024, in force 1 Jan 2025).

Source: the schedule uploaded to the knowledge base (`documents/knowledge_base/*Trinidad-tobago-customs.json`), a scanned PDF that was
OCR'd into HTML tables with the columns HS | CET | DESCRIPTION OF GOODS | DUTY RATE | UNIT(S). `refresh()` turns those tables into
`documents/tax_data/Trinidad and Tobago/tariff.json` (one record per 10-digit line, e.g. 0207.14.60). OCR is imperfect, so the parser
repairs what is certain (shifted columns, merged rows, "Frec" for Free) and flags the rest: a line whose duty rate could not be read
has status 'unreadable' and the calculator says so instead of guessing. Corrections go in `overrides.json` next to the tariff:
{"0206.49.06": {"rate": "40%"}} — they survive a refresh.

Rules applied (see the notes on every result): duty is charged on the CIF value (goods + freight + insurance); an ad valorem rate is a
percentage of it, a specific rate ("$92.28 per litre", in TT dollars) is multiplied by the quantity; CARICOM-origin goods are free of the
CET. VAT (12.5%, on CIF + duty) is shown but not counted: a VAT-registered importer credits it, and basic foods are zero-rated.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank
from .jamaica import CARICOM

FOLDER = DATA_ROOT / 'Trinidad and Tobago'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
TTD_PER_USD = 6.78  # TT dollars per US dollar (the central bank's rate barely moves); specific duties are written in TT$
VAT_RATE = 0.125

# the schedule says "fowls of the species Gallus domesticus", "bovine animals", "swine": everyday words are matched to its wording
SYNONYMS = {'chicken': 'fowl', 'beef': 'bovine', 'cattle': 'bovine', 'cow': 'bovine', 'pork': 'swine', 'pig': 'swine', 'hog': 'swine', 'lamb': 'sheep', 'mutton': 'sheep'}

HS = re.compile(r'\d{4}\.\d{2}')
HEADING = re.compile(r'\d{2}\.\d{2}')
CET = re.compile(r'\d{2}')
UNIT = re.compile(r'(?:kg|l|u|m|2u|12u)(?:[&/](?:kg|l|u|m|m2|m3|2u|ct|1))*', re.IGNORECASE)
RATE = re.compile(r'Free|\d+(?:\.\d+)?%|\$[\d.,]+ per [A-Za-z0-9 ]+')
FREE_TYPOS = re.compile(r"Fr[a-z]{1,3}'?", re.IGNORECASE)


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th'):
            self._cell = ''

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._row is not None and self._cell is not None:
            self._row.append(' '.join(self._cell.split()))
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data


def _rates(text: str) -> list[str]:
    """The duty rates written in a cell ("20%", "Free", "20% 20%" for two merged rows). OCR typos of Free are repaired."""
    text = (text or '').strip().strip("'")
    if FREE_TYPOS.fullmatch(text):
        return ['Free']
    return RATE.findall(text.replace('Frec', 'Free').replace('Frce', 'Free').replace('Frece', 'Free'))


def _is_rate(cell: str) -> bool:
    """The whole cell is a duty rate (not a description that merely contains a percentage)."""
    cell = (cell or '').strip().strip("'")
    return bool(cell) and (bool(FREE_TYPOS.fullmatch(cell)) or bool(re.fullmatch(rf'(?:{RATE.pattern})(?:\s+(?:{RATE.pattern}))*', cell)))


def _depth(description: str) -> int:
    return len(re.match(r'[\s\-–—]*', description).group(0).replace(' ', ''))


def _legible(text: str) -> bool:
    """False for OCR noise from upside-down or blurred scan regions ("po Jo bs e pe se"): too few real words."""
    words = re.findall(r'[A-Za-z]{3,}', text)
    return len(words) >= 1 and sum(len(word) for word in words) >= 0.5 * len(re.sub(r'[^A-Za-z]', '', text))


def _clean(description: str) -> str:
    return re.sub(r'^[\s\-–—]+', '', description).strip().rstrip(':').strip()


def parse_tariff(source: Path) -> dict:
    """Reads the OCR'd schedule and returns {'lines': [...], 'skipped': [...]} (see the module docstring)."""
    document = json.loads(source.read_text(encoding='utf-8'))
    lines: list[dict] = []
    skipped: list[dict] = []
    stack: list[tuple[int, str]] = []  # (dash depth, text) of the heading rows above
    seen: set[str] = set()

    for section in document['sections']:
        page = section.get('source_page')
        parser = _Tables()
        parser.feed(section.get('content') or '')
        for cells in parser.rows:
            cells = [cell for cell in cells]
            if not cells or cells[0] in ('HS', 'HS CET') or 'DESCRIPTION OF GOODS' in cells:
                continue
            first = cells[0].replace(' ', ' ')
            hs_codes = HS.findall(first)
            if not hs_codes:
                # no code: a sub-heading ("- Of bovine animals, frozen:") when it has a description and no rate
                text = max(cells, key=len) if cells else ''
                if text and not any(_is_rate(cell) for cell in cells) and len(text) > 3 and not HEADING.fullmatch(text) and _legible(text):
                    depth = _depth(text)
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    stack.append((depth, _clean(text)))
                elif any(_is_rate(cell) for cell in cells):
                    skipped.append({'page': page, 'cells': cells})
                continue
            rest = [cell for cell in cells[1:] if cell != '']
            cet_cells = [cell for cell in rest if re.fullmatch(r'\d{2}(?: \d{2})*', cell)]
            rate_cells = [cell for cell in rest if cell not in cet_cells and _is_rate(cell)]
            unit_cells = [cell for cell in rest if cell not in cet_cells and cell not in rate_cells and UNIT.fullmatch(cell.replace(' ', ''))]
            others = [cell for cell in rest if cell not in cet_cells and cell not in rate_cells and cell not in unit_cells]
            description = max(others, key=len) if others else ''
            rates = _rates(rate_cells[0]) if rate_cells else []
            unit = unit_cells[0] if unit_cells else None

            if HEADING.fullmatch(first.strip()) or (not rates and not cet_cells):
                # a heading row ("02.06 Edible offal …", "0303.99 | | -- Other:"): context for the lines below it
                depth = 0 if HEADING.fullmatch(first.strip()) else _depth(description)
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                if description and _legible(description):
                    stack.append((depth, _clean(description)))
                continue

            cet_codes = cet_cells[0].split() if cet_cells else []
            count = len(hs_codes)
            if count > 1 and len(cet_codes) != count:
                skipped.append({'page': page, 'cells': cells})
                continue
            for index in range(count):
                hs = hs_codes[index]
                cet = cet_codes[index] if index < len(cet_codes) else ''
                rate = rates[index] if index < len(rates) else (rates[0] if len(rates) == 1 and count == 1 else None)
                note = ''
                if len(rates) > 1 and count == 1:
                    rate, note = None, f'two rates were read on this row ({" / ".join(rates)}); check the schedule'
                status = 'ok' if rate and cet else ('review' if rate else 'unreadable')
                if rate and not cet:
                    note = 'the CET suffix of this line could not be read'
                if not rate and not note:
                    note = 'the duty rate could not be read (poor scan)'
                code = f'{hs}.{cet}' if cet else hs
                if code in seen:
                    skipped.append({'page': page, 'cells': cells})
                    continue
                seen.add(code)
                depth = _depth(description) if description else 0
                path = [text for d, text in stack if d < depth] if description else [text for _, text in stack]
                label = _clean(description) if _legible(description) else ''
                own = label or '(description not legible)'
                lines.append({
                    'code': code,
                    'hs': hs.replace('.', ''),
                    'description': own,
                    'path': ' > '.join([*path, own]),
                    'rate': rate,
                    'units': unit,
                    'page': page,
                    'status': status,
                    'note': note,
                })
                if depth == 0 and label:
                    stack.clear()
    return {'lines': lines, 'skipped': skipped}


def parse_rate(text: str | None) -> dict:
    """{'type': 'free'|'adv'|'specific'|'unreadable', ...} for a rate written in the schedule."""
    text = (text or '').strip()
    if text == 'Free':
        return {'type': 'free'}
    match = re.fullmatch(r'(\d+(?:\.\d+)?)%', text)
    if match:
        return {'type': 'adv', 'pct': float(match.group(1))}
    match = re.fullmatch(r'\$([\d.,]+) per (\d+)?\s*([A-Za-z]+)', text)
    if match:
        amount = float(match.group(1).replace(',', ''))
        per = int(match.group(2) or 1)
        unit = match.group(3).lower()
        return {'type': 'specific', 'ttd': amount, 'per': per, 'unit': 'litre' if unit.startswith('lit') else unit}
    return {'type': 'unreadable'}


class TrinidadCalculator(Calculator):
    name = 'Trinidad and Tobago'
    currency = 'TTD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.loaded_at: str | None = None
        self.skipped = 0

    # ------------------------------------------------------------ data
    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        """Re-reads the schedule uploaded to the knowledge base and rebuilds tariff.json."""
        sources = sorted(KNOWLEDGE_BASE.glob('*rinidad*customs*.json'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Trinidad and Tobago customs schedule is not in the knowledge base (documents/knowledge_base/*Trinidad-tobago-customs.json).')
        parsed = parse_tariff(sources[-1])
        FOLDER.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'source': sources[-1].name, 'lines': parsed['lines'], 'skipped': len(parsed['skipped'])}, ensure_ascii=False), encoding='utf-8')
        self._load()
        return self.info()

    def _load(self) -> None:
        self.lines, self.by_code = [], {}
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding='utf-8'))
        overrides_path = FOLDER / 'overrides.json'
        overrides = json.loads(overrides_path.read_text(encoding='utf-8')) if overrides_path.exists() else {}
        for line in data['lines']:
            override = overrides.get(line['code'])
            if override and override.get('rate'):
                line.update(rate=override['rate'], status='ok', note='rate corrected by hand (overrides.json)')
            self.lines.append(line)
            self.by_code[line['code']] = line
            self.by_code.setdefault(digits(line['code']), line)
        self.skipped = data.get('skipped', 0)
        self.loaded_at = datetime.fromtimestamp(self.path.stat().st_mtime).strftime('%Y-%m-%d')

    def _ensure(self) -> None:
        if not self.lines:
            self._load()

    def info(self) -> dict:
        self._ensure()
        unreadable = sum(1 for line in self.lines if line['status'] == 'unreadable')
        return {
            'country': self.name,
            'ready': bool(self.lines),
            'lines': len(self.lines),
            'source': 'CARICOM Common External Tariff — Legal Notice 218 of 2024 (knowledge base)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the customs schedule uploaded to the knowledge base (Trinidad-tobago-customs).',
            'currency': self.currency,
            'unreadable_lines': unreadable,
            'skipped_rows': self.skipped,
        }

    def signature(self, line: dict):
        return (line['rate'],)

    # ------------------------------------------------------------ lookup
    @staticmethod
    def _summary(line: dict) -> str:
        if not line['rate']:
            return 'Customs duty: rate not legible in the scan (page %s)' % line['page']
        return f"Customs duty {line['rate']}" + (' *' if line['status'] == 'review' else '')

    def _public(self, line: dict) -> dict:
        return {'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['units'], 'summary': self._summary(line), 'page': line['page'], 'status': line['status']}

    def search(self, query: str, limit: int = 30) -> list[dict]:
        self._ensure()
        query = (query or '').strip()
        if not query:
            return []
        if re.fullmatch(r'[\d.\s]+', query):
            prefix = digits(query)
            return [self._public(line) for line in self.lines if digits(line['code']).startswith(prefix)][:limit]
        words = [SYNONYMS.get(word, word) for word in query_words(query)]
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
        line = self.by_code.get((code or '').strip()) or self.by_code.get(digits(code))
        return self._public(line) if line else None

    # ------------------------------------------------------------ calculation
    def calculate(self, code: str, inputs: Inputs) -> Result:
        self._ensure()
        line = self.by_code.get((code or '').strip()) or self.by_code.get(digits(code))
        if line is None:
            raise ValueError(f'Tariff line {code} not found in the Trinidad and Tobago tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=[f"Customs (Common External Tariff) Order, 2024 (Legal Notice 218), tariff line {line['code']}, scan page {line['page']}"],
        )
        result.notes.append('Duty is charged on the CIF value (goods + freight + insurance), as Trinidad and Tobago Customs assesses it.')
        caricom = (inputs.origin or '').strip().lower() in CARICOM
        rate = parse_rate(line['rate'])

        if caricom:
            result.notes.append(f'{inputs.origin} is a CARICOM member: goods of CARICOM origin (with a certificate of origin) enter free of the Common External Tariff.')
            result.taxes.append(Tax('Customs duty', 0.0, '0% (CARICOM origin)', 'CIF value', f"CARICOM origin: duty waived (CET rate {line['rate'] or 'not legible'})"))
        elif rate['type'] == 'free':
            result.taxes.append(Tax('Customs duty', 0.0, 'Free', 'CIF value', 'free of duty'))
        elif rate['type'] == 'adv':
            result.taxes.append(Tax('Customs duty', cif * rate['pct'] / 100, f"{rate['pct']:g}%", 'CIF value', f"{money(cif)} × {rate['pct']:g}%"))
        elif rate['type'] == 'specific':
            per_unit = rate['ttd'] / rate['per'] / TTD_PER_USD
            quantity = inputs.quantity_units if rate['unit'] != 'kg' else inputs.quantity_kg
            label = f"TT${rate['ttd']:,.2f} per {rate['per'] if rate['per'] != 1 else ''}{rate['unit']}"
            if quantity is None:
                result.complete = False
                result.warnings.append(f"The duty is {label}: enter the quantity in {rate['unit']} to include it in the total.")
            else:
                result.taxes.append(Tax('Customs duty (specific)', quantity * per_unit, label, rate['unit'], f"{quantity:g} {rate['unit']} × TT${rate['ttd'] / rate['per']:,.2f} ÷ {TTD_PER_USD} TT$/US$"))
                result.notes.append(f'Specific duties are written in TT dollars and converted at TT$ {TTD_PER_USD} per US$.')
        else:
            result.complete = False
            result.warnings.append(f"The duty rate of line {line['code']} is not legible in the scanned schedule (page {line['page']}); the duty is not in the total. {line['note']}. Check the page and, if you read the rate, add it to overrides.json in the Trinidad and Tobago tariff folder.")
        if line['status'] == 'review' and rate['type'] != 'unreadable':
            result.warnings.append(f"This line was repaired when the scan was read: {line['note']}. Verify it on page {line['page']}.")

        duty = sum(tax.amount for tax in result.taxes)
        base = cif + duty
        result.taxes.append(
            Tax('Value added tax (VAT)', base * VAT_RATE, '12.5%', 'CIF value + duty', f'({money(cif)} + {money(duty)}) × 12.5%', recoverable=True,
                note='Not counted: a VAT-registered importer credits it as input tax, and basic foods and agricultural supplies are zero-rated (the VAT zero-rated list is not part of this tariff — check the product).')
        )
        if inputs.origin and not caricom:
            result.notes.append(f'No origin-based preference is applied for {inputs.origin} (only CARICOM origin is recognised); the standard CET rate applies.')
        result.warnings.append('Not included: import licences (Customs Act s.45 — e.g. live poultry, fresh fish, shrimp, coconut), sanitary/phytosanitary permits, excise or motor-vehicle taxes, the flat 30% duty for small non-commercial parcels (up to TT$425), brokerage and port charges.')
        return result
