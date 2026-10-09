"""Bahamas: import duty from the Tariff Act 2018 schedule (read BAHAMAS_RULES.md first).

Source: the knowledge-base document "bahamas-customs-1 duties explanation" (a .md of the Tariff Bill 2018 and its schedule, plain-text
columns). `refresh()` turns the schedule into `documents/tax_data/Bahamas/tariff.json`, one record per 8-digit line (0207.1420):
  general rate (Free / n%) · specific rate ($n BSD per unit) · maximum variable rate (the ceiling the Minister may impose by Order) ·
  preferential flag (EPA) · unit.
Tokens are classified by content, not by character position (columns drift between pages); a line whose rate could not be read is
'unreadable' and reported, never guessed.

Files next to the tariff (both optional, both survive a refresh):
  orders.json    {"0207.1420": {"rate": "60%", "order": "Tariff (Variable Rate) Order 2026", "date": "2026-01-15"}} — rates the Minister has
                 imposed by Order; they replace the General Rate (never above the line's maximum variable rate).
  overrides.json {"0206.1000": {"general": "Free"}} — hand corrections for unreadable lines.

Rules applied (see the notes on every result): duty on the CIF value; general rate unless an Order is in force; specific rates per unit;
CARICOM gets NO waiver (none is in the Act); the EPA preferential rate is not loaded (warned for EU-origin goods); VAT is shown, not counted.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank

FOLDER = DATA_ROOT / 'Bahamas'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
VAT_RATE = 0.10  # Bahamas VAT since 1 July 2022 (12% before) — public sources, NOT in the uploaded Act: verify
LB_PER_KG = 2.20462
LITRES_PER_UK_GALLON = 4.54609
EXCISE_CHAPTERS = {'24', '27', '40', '61', '63', '69', '70', '71', '84', '85', '87', '90', '91', '93'}  # Part B note 6
EPA_ORIGINS = {  # EU members (the CARIFORUM–EU EPA); the preferential rates themselves are in the Second Schedule, which is not loaded
    'austria', 'belgium', 'bulgaria', 'croatia', 'cyprus', 'czechia', 'czech republic', 'denmark', 'estonia', 'finland', 'france', 'germany',
    'greece', 'hungary', 'ireland', 'italy', 'latvia', 'lithuania', 'luxembourg', 'malta', 'netherlands', 'poland', 'portugal', 'romania',
    'slovakia', 'slovenia', 'spain', 'sweden',
}
UNIT_WORDS = {'pound', 'gallon', 'number', 'square yard', 'ton', 'pair', 'carat', 'square feet', 'cubic feet', 'barrel', 'proof gallon', 'feet'}

CODE = re.compile(r'^(\s+)(\d{4}\.\d{4}|\d{4}\.\d{2}|\d{2}\.\d{2})\s{2,}(\S.*)$')
RATE_TOKEN = re.compile(r'^(?:Free|\d+(?:\.\d+)?%)\.?$')
SPECIFIC = re.compile(r'^\$\s?([\d.,]+)\s*BSD')
NOISE = re.compile(r'^\s*(?:Page\s*-|P\s+age\s*-|\d+\s*$|Section\s|Chapter\s|TARIFF|CODE|Heading|Subheading|ARTICLE|DESCRIPTION|RATES OF DUTY|UNIT OF|MEASUREMENT|General|Rate|Variable|Preferential|Specific|Maximum|Number\s*$|```|>)', re.IGNORECASE)


def _depth(text: str) -> int:
    return len(re.match(r'[\s\-–—]*', text).group(0).replace(' ', ''))


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^[\s\-–—]+', '', text)).strip().rstrip(':').strip()


def parse_tariff(source: Path) -> dict:
    """Reads the schedule text and returns {'lines': [...], 'skipped': n}. See the module docstring."""
    stack: list[tuple[int, str]] = []  # (dash depth, text) of the heading rows above
    lines: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    page = 0
    last: dict | None = None  # the row whose wrapped description the next indented text lines continue
    in_table = False
    description_indent = 0

    def add_heading(depth: int, text: str):
        while stack and stack[-1][0] >= depth:
            stack.pop()
        item = {'depth': depth, 'text': text}
        stack.append((depth, text))
        return item

    for raw in source.read_text(encoding='utf-8').split('\n'):
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            page, last, in_table = int(marker.group(1)), None, False
            continue
        if 'ARTICLE' in raw or 'Subheading' in raw:
            in_table = True
            continue
        if not in_table or not raw.strip():
            continue
        match = CODE.match(raw)
        if match:
            code, rest = match.group(2), match.group(3)
            description_indent = match.start(3)
            parts = re.split(r'\s{2,}', rest.strip())
            description, tokens = parts[0], parts[1:]
            if not re.fullmatch(r'\d{4}\.\d{4}', code):  # 4- and 6-digit rows are headings: context for the lines below
                last = {'heading': True, 'depth': 0 if len(code) == 5 else _depth(description), 'text': description, 'indent': description_indent}
                last['stack_index'] = None
                depth = last['depth']
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                stack.append((depth, description))
                last['entry'] = stack[-1]
                last['stack_pos'] = len(stack) - 1
                continue
            record = {'code': code, 'description': description, 'tokens': tokens, 'page': page, 'depth': _depth(description), 'stack': list(stack)}
            record['indent'] = description_indent
            last = record
            lines.append(record)
            continue
        # text without a code: a sub-heading ("- Of bovine animals, frozen :"), or the wrapped part of the row above
        text = raw.strip()
        if NOISE.match(raw) or re.fullmatch(r'\d+', text):
            continue
        indent = len(raw) - len(raw.lstrip())
        if text.startswith('-') and last is not None and abs(indent - last['indent']) <= 3:
            depth = _depth(text)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, text))
            last = {'heading': True, 'depth': depth, 'text': text, 'indent': last['indent'], 'stack_pos': len(stack) - 1}
        elif last is not None and abs(indent - last['indent']) <= 3:
            if last.get('heading'):
                pos = last['stack_pos']
                if pos < len(stack):
                    stack[pos] = (stack[pos][0], stack[pos][1] + ' ' + text)
            else:
                last['description'] += ' ' + text
        # text far to the right (the "per imp. Gal" under a specific rate) carries nothing the calculator needs

    out = []
    for record in lines:
        general = maximum = specific = None
        preferential = False
        unit = None
        unknown = []
        percent_tokens = []
        for token in record['tokens']:
            token = token.strip()
            if RATE_TOKEN.match(token):
                percent_tokens.append(token.rstrip('.'))
            elif token == 'EPA':
                preferential = True
            elif SPECIFIC.match(token):
                specific = float(SPECIFIC.match(token).group(1).replace(',', ''))
            elif re.sub(r'^\d+\s*', '', token).lower().rstrip('.') in UNIT_WORDS:
                unit = token.lower().rstrip('.')
            elif len(token) > 12 and ' ' in token:  # the wrapped end of the description that shares the row's line
                record['description'] += ' ' + token
            else:
                unknown.append(token)
        if percent_tokens:
            general = percent_tokens[0]
        if len(percent_tokens) > 1:
            maximum = percent_tokens[-1]
        # a single token that is a ceiling (100%/300%) with no General rate, and no specific rate, is ambiguous
        status, note = 'ok', ''
        if general is None and specific is None:
            status, note = 'unreadable', 'no duty rate could be read for this line'
        elif len(percent_tokens) == 1 and percent_tokens[0] in ('100%', '200%', '300%') and specific is None and not record['tokens'][0].startswith(percent_tokens[0]):
            status, note = 'review', f'only {percent_tokens[0]} was read; it may be the maximum variable rate with no general rate'
        if unknown and general is None and specific is None:
            note = (note + f' unrecognised text in the rate columns: {" | ".join(unknown)}').strip()
        path = [text for d, text in record['stack'] if d < record['depth']]
        label = _clean(record['description']) or '(description not legible)'
        if record['code'] in seen:
            skipped += 1
            continue
        seen.add(record['code'])
        out.append({
            'code': record['code'],
            'hs': record['code'].replace('.', '')[:6],
            'description': label,
            'path': ' > '.join([*[_clean(text) for text in path if _clean(text)], label]),
            'general': general,
            'specific_usd': specific,
            'maximum_variable': maximum,
            'preferential': preferential,
            'units': unit,
            'page': record['page'],
            'status': status,
            'note': note,
        })
    return {'lines': out, 'skipped': skipped}


def _pct(rate: str | None) -> float | None:
    if rate is None:
        return None
    if rate == 'Free':
        return 0.0
    return float(rate.rstrip('%'))


class BahamasCalculator(Calculator):
    name = 'Bahamas'
    currency = 'BSD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.loaded_at: str | None = None
        self.orders: dict = {}

    # ------------------------------------------------------------ data
    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        """Re-reads the schedule uploaded to the knowledge base and rebuilds tariff.json."""
        sources = sorted(KNOWLEDGE_BASE.glob('*ahamas*customs*.md'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Bahamas customs schedule is not in the knowledge base (documents/knowledge_base/*bahamas-customs*.md).')
        parsed = parse_tariff(sources[-1])
        FOLDER.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'source': sources[-1].name, 'lines': parsed['lines'], 'skipped': parsed['skipped']}, ensure_ascii=False), encoding='utf-8')
        self._load()
        return self.info()

    def _read_json(self, name: str) -> dict:
        path = FOLDER / name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def _load(self) -> None:
        self.lines, self.by_code = [], {}
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding='utf-8'))
        overrides = self._read_json('overrides.json')
        self.orders = self._read_json('orders.json')
        for line in data['lines']:
            override = overrides.get(line['code'])
            if override:
                line.update({key: value for key, value in override.items() if key in ('general', 'specific_usd', 'maximum_variable', 'units')}, status='ok', note='corrected by hand (overrides.json)')
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
            'source': 'Bahamas Tariff Act 2018 schedule (knowledge base)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the Bahamas customs schedule uploaded to the knowledge base.',
            'currency': self.currency,
            'unreadable_lines': sum(1 for line in self.lines if line['status'] == 'unreadable'),
            'review_lines': sum(1 for line in self.lines if line['status'] == 'review'),
            'orders_in_force': len(self.orders),
        }

    def signature(self, line: dict):
        return (line['general'], line['specific_usd'])

    # ------------------------------------------------------------ lookup
    def _summary(self, line: dict) -> str:
        parts = []
        if line['general']:
            parts.append(f"Customs duty {line['general']}")
        if line['specific_usd']:
            parts.append(f"${line['specific_usd']:g} BSD per {line['units'] or 'unit'}")
        if line['maximum_variable']:
            parts.append(f"up to {line['maximum_variable']} by Order")
        if line['code'] in self.orders:
            parts.append(f"Order in force: {self.orders[line['code']].get('rate')}")
        return '; '.join(parts) or f"rate not legible in the scan (page {line['page']})"

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
        words = query_words(query)
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
            raise ValueError(f'Tariff line {code} not found in the Bahamas tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=[f"Bahamas Tariff Act 2018, schedule line {line['code']}, scan page {line['page']}"],
        )
        result.notes.append('Duty is charged on the CIF value (goods + freight + insurance); the Bahamian dollar is pegged 1:1 to the US dollar.')

        # ---- ad valorem: the General Rate, or the rate the Minister imposed by Order
        general = _pct(line['general'])
        ceiling = _pct(line['maximum_variable'])
        order = self.orders.get(line['code'])
        rate, rate_text = general, line['general']
        if order and order.get('rate'):
            ordered = _pct(order['rate'])
            if ordered is not None and ceiling is not None and ordered > ceiling:
                result.warnings.append(f"The Order rate {order['rate']} for this line is above its maximum variable rate {line['maximum_variable']}; the Order was ignored.")
            elif ordered is not None:
                rate, rate_text = ordered, order['rate']
                result.notes.append(f"A rate imposed by Order is in force for this line: {order['rate']} ({order.get('order', 'Order')}{', ' + order['date'] if order.get('date') else ''}); it replaces the General Rate {line['general']}.")
        if rate is not None:
            result.taxes.append(Tax('Customs duty', cif * rate / 100, rate_text or '', 'CIF value', f'{money(cif)} × {rate:g}%' if rate else 'free of duty'))
        elif line['specific_usd'] is None:
            result.complete = False
            result.warnings.append(f"The duty rate of line {line['code']} is not legible in the scan (page {line['page']}); the duty is not in the total. {line['note']}. Check the page and, if you read the rate, add it to overrides.json in the Bahamas tariff folder.")
        if line['status'] == 'review':
            result.warnings.append(f"Verify this line on page {line['page']}: {line['note']}.")

        # ---- specific rate ($ BSD per unit of the line's unit)
        if line['specific_usd']:
            unit = (line['units'] or '').lower()
            if unit == 'pound' and inputs.quantity_kg is not None:
                quantity, label = inputs.quantity_kg * LB_PER_KG, 'pound'
            else:
                quantity, label = inputs.quantity_units, unit or 'unit'
            if quantity is None:
                result.complete = False
                result.warnings.append(f"A specific duty of ${line['specific_usd']:g} BSD per {label} also applies: enter the quantity in {label} to include it in the total.")
            else:
                result.taxes.append(Tax('Customs duty (specific)', quantity * line['specific_usd'], f"${line['specific_usd']:g} BSD per {label}", label, f"{quantity:,.2f} {label} × ${line['specific_usd']:g}"))
                if unit == 'gallon':
                    result.notes.append(f'The gallon in the Bahamian tariff is the imperial (UK) gallon, {LITRES_PER_UK_GALLON} litres.')

        # ---- the variable rate, preferences, excise
        if line['maximum_variable'] and not (order and order.get('rate')):
            result.warnings.append(f"The Minister may impose a rate of up to {line['maximum_variable']} on this product by Order (it would replace the General Rate {line['general']}). No Order is recorded for it here — check the Gazette; add one to orders.json when it applies.")
        if line['preferential'] and (inputs.origin or '').strip().lower() in EPA_ORIGINS:
            result.warnings.append(f'{inputs.origin} is an EPA partner and this line has an EPA preferential rate (Second Schedule of the Tariff Act). That schedule is not loaded: the General Rate is shown, which may be higher than the preferential rate.')
        if inputs.origin:
            result.notes.append(f'No origin preference is applied for {inputs.origin}: the Act gives none to CARICOM or to {inputs.origin}; only the EPA column exists.')
        chapter = digits(line['code'])[:2]
        if chapter in EXCISE_CHAPTERS:
            result.complete = False
            result.warnings.append(f'Goods of chapter {chapter} can also carry excise tax collected at entry (Excise Act 2018, Tariff Act Part B note 6). Excise rates are not loaded, so the total is a minimum.')
        if line['code'].startswith(('0801', '0802', '0803', '0804', '0805', '0806', '0807', '0808', '0809', '0810', '0811', '0812', '0813', '1201', '1202', '1203', '1204', '1205', '1206', '1207', '1208', '1209', '1210', '1211', '1212', '1213', '1214')) and 'unpackaged' in line['path'].lower() + line['description'].lower():
            result.notes.append('"Unpackaged" means a package over 20 pounds (Tariff Act Part B 2(e)); this line applies to such packages. Packages of 20 pounds or less are a different tariff line.')

        # ---- VAT (not in the uploaded Act)
        duty = sum(tax.amount for tax in result.taxes)
        result.taxes.append(
            Tax('Value added tax (VAT)', (cif + duty) * VAT_RATE, '10%', 'CIF value + duty', f'({money(cif)} + {money(duty)}) × 10%', recoverable=True,
                note='Not counted: a VAT-registered importer credits it, and basic foods are zero-rated. The VAT Act is not in the uploaded document — the 10% rate comes from public sources, verify it.')
        )
        result.warnings.append('Not included: Customs fees and any stamp tax, anti-dumping/countervailing duties (s.10), the 1% ad valorem charge on goods entered into a bonded warehouse (s.9), exemptions under Chapter 98 (farmers, fishermen, hotels, …), import permits and health certificates.')
        return result
