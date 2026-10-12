"""Turks and Caicos Islands: import duty from the Customs Tariff 2010 (Customs Tariff (General) Order 2010, L.N. 13/2010, in force 1 Aug 2010) plus the charges
of the Customs Ordinance, Cap. 19.04 (both uploaded to the knowledge base: "tariffs-duties 2010 turks aand Caicos" and "turks and caicos customs ordinance").

The tariff table (pp. 33-835 of the first file) has the columns HEADING No. | TARIFF CODE (7 digits, e.g. 0207.271) | DESCRIPTION | UNIT | SUPP. UNIT | IMPORT DUTY RATE |
EXPORT DUTY RATE. Import rates are plain percentages (food is mostly 0%), specific amounts ($11.91/gal beer, $42.38/gal spirits, $45.64/lb tobacco, $90.52/1000 cigarettes,
$0.09-$0.44/gal fuel) or, for vehicles, a percentage on the LANDED COST (printed on the line below the rate). `refresh()` writes `documents/tax_data/Turks and Caicos/tariff.json`.

Rules applied (see the notes on every result; TURKS_AND_CAICOS_RULES.md has the page references):
  * duty on the value of the goods (the "normal price": exclusive of freight and insurance, Ordinance s.93); LANDED COST lines (vehicles) on goods + freight + insurance;
  * customs processing fee: 7.5% of the value of goods imported, on ALL imports including duty-free goods (s.137);
  * charge on insurance and freight: 7.5% of the freight and insurance cost (s.135; 5% for building materials; none for motor vehicles and petroleum);
  * additional duty on fuel: US$0.85 per imperial gallon (Customs (Additional Import Duty on Fuel) Order), on top of the tariff duty;
  * no preference for CARICOM: the Islands are not a CARICOM customs-union member in these files; no VAT or sales tax is mentioned in them.
Hand corrections: `overrides.json` next to the tariff, {"0207.271": {"rate": "0%"}}.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank

FOLDER = DATA_ROOT / 'Turks and Caicos'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
TABLE_PAGES = range(33, 836)
LB_PER_KG = 2.20462
PROCESSING_FEE = 0.075
FREIGHT_CHARGE = 0.075
BUILDING_MATERIAL_FREIGHT_CHARGE = 0.05  # L.N. 39/2013: sand, cement, blocks, steel
FUEL_DUTY_USD_PER_GALLON = 0.85  # additional duty on fuel (L.N. 11/2010, 12/2011, 38/2013); the "gal" of the tariff is the imperial gallon
FUEL_CODES = ('2710.110', '2710.191', '2710.192', '2710.193', '2710.194', '2710.195', '2710.196')
BUILDING_MATERIAL_PREFIXES = ('2505', '2523', '6810', '7213')  # Customs (Charge on Insurance and Freight)(Building Materials) Order, Schedule

SYNONYMS = {'chicken': 'fowl', 'beef': 'bovine', 'cattle': 'bovine', 'cow': 'bovine', 'pork': 'swine', 'pig': 'swine', 'hog': 'swine', 'lamb': 'sheep', 'mutton': 'sheep'}
CODE = re.compile(r'^(\s+)(?:(\d{2}\.\d{2})\s+)?(\d{4}\.\d{3})\s+(.*)$')  # an optional heading number (07.02) may share the line with the tariff code
HEADING = re.compile(r'^\s{6,30}(\d{2}\.\d{2})(?:\s{2,}(.*))?$')
RATE = re.compile(r'^(?:\d+(?:\.\d+)?%|\$\s?\d[\d.,]*\s*/\s*(?:gal|lb|1000|l|kg|no))$')
UNITS = {'lb', 'lb.', 'no', 'no.', 'gal', 'l', 'kg', 'pr', 'pr.', '2u', '2u.', '12u', 'ton', 'qt', 'cc', 'cm', 'mm', 'kw', 'kva'}
HEADER_WORDS = re.compile(r'^\s*(?:SECTION\b|CHAPTER\b|HEADING|No\.?\s*$|TARIFF\b|CODE\b|DESCRIPTION|UNIT\b|SUPP\.|IMPORT\b|EXPORT\b|DUTY\b|RATE\b|\d{1,4}\s*$|```|>)', re.IGNORECASE)


def _depth(text: str) -> int:
    return len(re.match(r'[\s\-–—]*', text).group(0).replace(' ', ''))


def _clean(text: str) -> str:
    text = re.sub(r'^[\s\-–—]+', '', text)
    text = re.sub(r'^([A-Z])\s{1,2}(?=[a-z])', r'\1', text)  # the OCR splits the first letter of some headings ("O  ther")
    return re.sub(r'\s+', ' ', text).strip().rstrip(':').strip()


def _is_unit(token: str) -> bool:
    return token.lower().rstrip('.') in {unit.rstrip('.') for unit in UNITS} or bool(re.fullmatch(r'\d*u\.?', token.lower()))


def _tokens(text: str) -> tuple[str, list[str]]:
    """(description part, cells) of a line's text right of the code: cells are the 2+-space separated pieces that are units, rates or LANDED COST."""
    parts = [part.strip() for part in re.split(r'\s{2,}', text.strip()) if part.strip()]
    cells: list[str] = []
    while parts and (RATE.match(parts[-1]) or _is_unit(parts[-1]) or parts[-1].upper() == 'LANDED COST'):
        cells.insert(0, parts.pop())
    return ' '.join(parts), cells


def parse_tariff(source: Path) -> dict:
    text = source.read_text(encoding='utf-8').split('\n')
    # pages that carry code rows but no column-header line (the table simply continues from the previous page) are table pages from their first line
    has_header: set[int] = set()
    has_code: set[int] = set()
    current = -1
    for raw in text:
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            current = int(marker.group(1))
        elif re.search(r'DESCRIPTION', raw) and re.search(r'UNIT', raw):
            has_header.add(current)
        elif CODE.match(raw):
            has_code.add(current)
    headerless = has_code - has_header
    rows: list[dict] = []
    stack: list[tuple[int, str]] = []
    heading = ''
    heading_open = False
    cur: dict | None = None
    page = -1
    in_table = False

    def finish():
        nonlocal cur
        if cur is not None:
            rows.append(cur)
        cur = None

    for raw in text:
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            finish()
            page = int(marker.group(1))
            in_table = page in headerless
            continue
        if page not in TABLE_PAGES or not raw.strip():
            continue
        if re.search(r'DESCRIPTION', raw) and re.search(r'UNIT', raw):
            in_table = True
            continue
        if not in_table or HEADER_WORDS.match(raw):
            continue
        code = CODE.match(raw)
        if code:
            finish()
            heading_open = False
            description, cells = _tokens(code.group(4))
            if code.group(2):  # the heading is a single line with its only tariff code: it has no heading above it
                heading, stack = '', []
            cur = {'code': code.group(3), 'page': page, 'description': description, 'cells': cells, 'depth': _depth(description), 'stack': list(stack), 'heading': heading, 'landed': False}
            continue
        head = HEADING.match(raw)
        if head and not re.search(r'\d{4}\.\d', raw):
            finish()
            heading = _clean(head.group(2) or '')
            heading_open = not heading.endswith('.')
            stack = []
            continue
        stripped = raw.strip()
        if cur is not None:
            description, cells = _tokens(stripped)
            if not description and cells:  # a line with only units / rate / LANDED COST belongs to the row above
                for cell in cells:
                    if cell.upper() == 'LANDED COST':
                        cur['landed'] = True
                    else:
                        cur['cells'].append(cell)
                continue
            if stripped.startswith('-') and any(RATE.match(c) for c in cur['cells']):
                finish()  # an un-coded sub-heading ("-  Of turkeys :") for the rows after it
            else:
                cur['description'] = (cur['description'] + ' ' + description).strip()
                for cell in cells:
                    if cell.upper() == 'LANDED COST':
                        cur['landed'] = True
                    else:
                        cur['cells'].append(cell)
                continue
        if stripped.startswith('-'):
            depth = _depth(stripped)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, stripped))
        elif heading_open:
            heading = (heading + ' ' + _clean(stripped)).strip()
            heading_open = not heading.endswith('.')
        else:
            stack_text = stripped
            if stack:  # a wrapped line of an un-coded sub-heading
                stack[-1] = (stack[-1][0], stack[-1][1] + ' ' + stack_text)
    finish()

    lines: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    for row in rows:
        rate = next((cell for cell in row['cells'] if RATE.match(cell)), None)
        units = [cell for cell in row['cells'] if _is_unit(cell)]
        if row['code'] in seen:
            skipped += 1
            continue
        seen.add(row['code'])
        label = _clean(row['description']) or '(description not legible)'
        path = [row['heading']] if row['heading'] else []
        path += [_clean(text) for depth, text in row['stack'] if depth < row['depth'] and _clean(text)]
        specific = None
        pct = None
        if rate:
            if rate.endswith('%'):
                pct = rate.replace(' ', '')
            else:
                specific = re.sub(r'\s+', '', rate)
        lines.append({
            'code': row['code'], 'hs': digits(row['code'])[:6], 'description': label, 'path': ' > '.join([*path, label]), 'rate': pct, 'specific': specific,
            'landed_cost': row['landed'], 'unit': units[0] if units else None, 'supp_unit': units[1] if len(units) > 1 else None, 'page': row['page'],
            'status': 'ok' if rate else 'unreadable', 'note': '' if rate else 'no import duty rate could be read for this line',
        })
    return {'lines': lines, 'skipped': skipped}


class TurksCaicosCalculator(Calculator):
    name = 'Turks and Caicos Islands'
    currency = 'USD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.loaded_at: str | None = None

    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        sources = sorted(KNOWLEDGE_BASE.glob('*tariffs-duties*urks*.md'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Turks and Caicos tariff is not in the knowledge base (documents/knowledge_base/*tariffs-duties 2010 turks*.md).')
        parsed = parse_tariff(sources[-1])
        FOLDER.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'source': sources[-1].name, **parsed}, ensure_ascii=False), encoding='utf-8')
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
                line.update(rate=override['rate'], specific=None, status='ok', note='rate corrected by hand (overrides.json)')
            self.lines.append(line)
            self.by_code[line['code']] = line
            self.by_code.setdefault(digits(line['code']), line)
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
            'source': 'Customs Tariff (General) Order 2010, L.N. 13/2010 (knowledge base) + Customs Ordinance Cap. 19.04',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the Turks and Caicos Customs Tariff 2010 uploaded to the knowledge base.',
            'currency': self.currency,
            'unreadable_lines': sum(1 for line in self.lines if line['status'] == 'unreadable'),
            'specific_rate_lines': sum(1 for line in self.lines if line['specific']),
            'landed_cost_lines': sum(1 for line in self.lines if line['landed_cost']),
        }

    def signature(self, line: dict):
        return (line['rate'], line['specific'], line['landed_cost'])

    # ------------------------------------------------------------ lookup
    @staticmethod
    def _summary(line: dict) -> str:
        if line['specific']:
            return f"Customs duty {line['specific']}"
        if line['rate']:
            return f"Customs duty {line['rate']}" + (' on landed cost' if line['landed_cost'] else '')
        return 'Customs duty: rate not legible in the scan'

    def _public(self, line: dict) -> dict:
        return {'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['unit'], 'summary': self._summary(line), 'page': line['page'], 'status': line['status']}

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
        scored = [(key, line) for line in self.lines if (key := rank(line, words)) is not None]
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
            raise ValueError(f'Tariff line {code} not found in the Turks and Caicos tariff.')
        goods = inputs.goods_value_usd
        shipping = inputs.freight_usd + inputs.insurance_usd
        base = goods + shipping if line['landed_cost'] else goods
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'Landed cost' if line['landed_cost'] else 'Value of the goods (normal price, without freight and insurance)', 'amount_usd': round(base, 2),
                         'formula': f'goods {money(goods)}' + (f' + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}' if line['landed_cost'] else ' (freight and insurance are not part of the duty value)')},
            sources=[f"Customs Tariff (General) Order 2010, tariff code {line['code']}, page {line['page']} of the file; Customs Ordinance Cap. 19.04 ss.93, 135, 137"],
        )
        result.notes.append('Duty value is the "normal price" of the goods, exclusive of freight and insurance (Customs Ordinance s.93); vehicles and other LANDED COST lines include freight and insurance.')

        # ---- tariff duty
        if line['specific']:
            amount_text, unit = line['specific'].lstrip('$').split('/', 1)
            amount = float(amount_text.replace(',', ''))
            if unit == 'lb':
                quantity, label = (inputs.quantity_kg * LB_PER_KG if inputs.quantity_kg is not None else None), 'lb'
                per = amount
            elif unit == '1000':
                quantity, label, per = (inputs.quantity_units / 1000 if inputs.quantity_units is not None else None), 'thousand', amount
            else:
                quantity, label, per = inputs.quantity_units, unit, amount
            if quantity is None:
                result.complete = False
                result.warnings.append(f"The duty is {line['specific']}: enter the quantity in {'kg' if unit == 'lb' else label} to include it in the total.")
            else:
                result.taxes.append(Tax('Customs duty (specific)', quantity * per, line['specific'], label, f'{quantity:,.2f} {label} × ${per:g}'))
                if unit == 'gal':
                    result.notes.append('The tariff gallon is the imperial gallon (4.546 litres).')
        elif line['rate']:
            pct = float(line['rate'].rstrip('%'))
            result.taxes.append(Tax('Customs duty', base * pct / 100, line['rate'], 'landed cost' if line['landed_cost'] else 'value of goods', f'{money(base)} × {pct:g}%'))
        else:
            result.complete = False
            result.warnings.append(f"The import duty rate of line {line['code']} could not be read from the file (page {line['page']}); the duty is not in the total. Add it to overrides.json in the Turks and Caicos tariff folder.")

        # ---- additional duty on fuel
        if line['code'] in FUEL_CODES:
            if inputs.quantity_units is None:
                result.complete = False
                result.warnings.append(f'Fuel also pays an additional duty of US${FUEL_DUTY_USD_PER_GALLON:.2f} per gallon: enter the quantity in imperial gallons to include it.')
            else:
                result.taxes.append(Tax('Additional import duty on fuel', inputs.quantity_units * FUEL_DUTY_USD_PER_GALLON, f'US${FUEL_DUTY_USD_PER_GALLON:.2f}/gal', 'gal', f'{inputs.quantity_units:,.2f} gal × US${FUEL_DUTY_USD_PER_GALLON:.2f}'))

        # ---- customs processing fee: 7.5% of the value of goods, on every import (also duty-free goods)
        result.taxes.append(Tax('Customs processing fee', goods * PROCESSING_FEE, '7.5%', 'value of goods', f'{money(goods)} × 7.5%', note='Charged on all imports, including goods with 0% duty (Customs Ordinance s.137). Not payable by the persons listed in Schedule 3 of the Ordinance.'))

        # ---- charge on insurance and freight: 7.5% (5% for building materials); none on vehicles and petroleum
        digits_code = digits(line['code'])
        exempt = line['landed_cost'] or digits_code.startswith('2709') or digits_code.startswith('2710') or digits_code.startswith('87')
        if exempt:
            result.notes.append('No charge on insurance and freight: it does not apply to motor vehicles and petroleum (Ordinance s.135(3)).')
        elif shipping > 0:
            rate = BUILDING_MATERIAL_FREIGHT_CHARGE if digits_code.startswith(BUILDING_MATERIAL_PREFIXES) else FREIGHT_CHARGE
            result.taxes.append(Tax('Charge on insurance and freight', shipping * rate, f'{rate * 100:g}%', 'freight + insurance', f'{money(shipping)} × {rate * 100:g}%'))
        else:
            result.warnings.append('A 7.5% charge on the cost of insurance and freight (5% on building materials) applies to every import; no freight or insurance was entered, so it is not in the total.')

        if inputs.origin:
            result.notes.append(f'No origin preference is applied for {inputs.origin}: the Governor may vary duty by country of origin (Ordinance s.74) but no such order is in these files.')
        result.warnings.append('Not included: exemptions under Part IV of the Tariff Order (government, public servants, charities, approved purposes), the flat 33% rate for baggage and small personal consignments, duty-free-shop rules, import licences and sanitary/phytosanitary permits. '
                               'The tariff is the 2010 Order; the Customs Tariff was later amended (L.N. 16/2010, 38/2011) and these amendments are not in the file.')
        return result
