"""Grenada: import duty from the CARICOM Common External Tariff as set out in Grenada's Customs Act, Chapter 75A ("Grenada customs duties" in
the knowledge base: Fifth Schedule, SRO 42 of 2009, HS 2007, in force 1 February 2010) plus the Rum and Whisky import-duty Orders.

The schedule has columns HEADING | DESCRIPTION OF GOODS | RATE OF DUTY | UNIT(S) | SITC. Descriptions are vertically centred, so the text of a row can sit
above or below its code line and the rate can be on the last description line; `parse_tariff` handles that. `refresh()` writes
`documents/tax_data/Grenada/tariff.json` (one record per 8-digit line, e.g. 0207.14.20).

Lists A and C (pp.592-611 of the file) give, per item, the CET rate and the rate each member state applies. The Grenada column is the 6th value
(CET, ANT&BAR, BDS, BEL, DOM, GREN …); it replaces the schedule rate when the row is readable. In this file the schedule and the lists agree for
every comparable line (checked by the tests).

Rules applied: duty on the CIF value; ad valorem, or specific (rum and whisky, by their Orders; some lines carry $ or ¢ per unit); CARICOM origin
= free; the EPA tariff orders listed in the file's index are NOT in the file, so EU origin gets the normal rate plus a warning; VAT 15% (from public
sources, not in the file) is shown, not counted. See BAHAMAS_RULES.md for the sibling approach. Hand corrections: `overrides.json` next to the
tariff, {"0201.10.00": {"rate": "30%"}}.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, higher_rate, money, query_words, rank
from .jamaica import CARICOM

FOLDER = DATA_ROOT / 'Grenada'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
XCD_PER_USD = 2.70
VAT_RATE = 0.15  # Grenada VAT — public sources, NOT in the uploaded file: verify
LITRES_PER_UK_GALLON = 4.54609
GRENADA_COLUMN = 5  # CET, ANT&BAR, BDS, BEL, DOM, GRENADA, GUY, JAM, MONT, K&N, LUCIA, V&G, SUR, T&T (Lists A and C)
EPA_ORIGINS = {
    'austria', 'belgium', 'bulgaria', 'croatia', 'cyprus', 'czechia', 'czech republic', 'denmark', 'estonia', 'finland', 'france', 'germany',
    'greece', 'hungary', 'ireland', 'italy', 'latvia', 'lithuania', 'luxembourg', 'malta', 'netherlands', 'poland', 'portugal', 'romania',
    'slovakia', 'slovenia', 'spain', 'sweden',
}
# Customs (Import Duty on Rum / Whisky) Orders, SRO 30 and 33 of 1961: EC$ per liquid gallon (strength not above proof), "general" rate.
SPIRIT_ORDERS = {
    '2208.40': {'name': 'rum', 'general_xcd_per_gallon': 9.36, 'preferential_xcd_per_gallon': 9.00},
    '2208.30': {'name': 'whisky', 'general_xcd_per_gallon': 15.36, 'preferential_xcd_per_gallon': 15.00},
}

CODE8 = re.compile(r'^(\s+)(\d{4}\.\d{2}\.\d{2})(?:\s{2,}(.*))?$')
HEAD4 = re.compile(r'^(\s+)(\d{2}\.\d{2})(?:\s{2,}(.*))?$')
RATE = re.compile(r'^(?:Free|\d+(?:\.\d+)?%(?:\s*/\s*\d+(?:\.\d+)?%)?|\$\s?[\d.,]+(?:\s*(?:per|/)\s*\S+)?|\d+¢(?:\s*per\s*\S+)?)$')
UNIT = re.compile(r'^(?:kg|Kg)\b.*|^(?:l|u|m|m2|m3)\b.*$')
SITC = re.compile(r'^\d{3}(?:\.\d+)?$')
NOISE = re.compile(r'^\s*(?:RATE\s*OF|RATEOF|HEADING|DESCRIPTION|UNIT\(S\)|SITC|DUTY|UTY|REV|3\s*$|CHAPTER\b|Note|Notes|```|>)', re.IGNORECASE)

LIST_TOKEN = re.compile(r'\d+(?:\.\d+)?%/\s*\d+(?:\.\d+)?%|\d+(?:\.\d+)?%/|\d+(?:\.\d+)?¢|\$\s?\d[\d.,]*(?:\s+per\s+(?:Imp\.\s+)?(?:litre|L\.?\s?gal\.?|gal\.?|head|kg|100\s?kg))?|Free|\d+(?:\.\d+)?%')
LIST_CODE = re.compile(r'(\d{4})\s?\.\s?(\d{2})\s?\.\s?(\d{2})')


def _list_tokens(line: str) -> list[str]:
    line = re.sub(r'F\s+r\s*e\s*e', 'Free', line)  # OCR split "F  ree"
    line = re.sub(r'(?<![\d.$])(\d)\s+(\d{1,2}%)', lambda m: m.group(1) + m.group(2), line)  # "3  0%" -> "30%"
    line = re.sub(r'(\d+%)\s*/\s*(\d+%)', lambda m: m.group(1) + '/' + m.group(2), line)  # "30%/ 35%" is one value
    line = re.sub(r'\$\s+(\d)', lambda m: '$' + m.group(1), line)
    tokens = [token.strip() for token in LIST_TOKEN.findall(line)]
    return tokens[-14:] if len(tokens) > 14 else tokens  # the values end the row; numbers in a wrapped description come before them


def parse_list_rows(lines: list[tuple[str, str]]) -> dict:
    """[(list letter, line)] of Lists A and C -> {code: {'rate': Grenada's rate, 'list': 'A', 'cet': the CET rate}}.
    A row is read only when it carries all 14 values (CET + 13 states); a row whose values wrap onto the next line is completed from it."""
    national: dict = {}
    pending: tuple[str, str] | None = None
    for letter, line in lines:
        codes = LIST_CODE.findall(line)
        tokens = _list_tokens(line)
        if codes:
            code = '.'.join(codes[-1])
            if len(tokens) == 14:
                national[code] = {'rate': tokens[GRENADA_COLUMN], 'list': letter, 'cet': tokens[0]}
                pending = None
            else:
                pending = (code, letter)
        elif pending and len(tokens) == 14:
            national[pending[0]] = {'rate': tokens[GRENADA_COLUMN], 'list': pending[1], 'cet': tokens[0]}
            pending = None
    return national


def _split_row(text: str) -> tuple[str, str | None, str | None, str | None]:
    """(description part, rate, unit, sitc) of the text right of the code (or of a continuation line)."""
    parts = [part.strip() for part in re.split(r'\s{2,}', text.strip()) if part.strip()]
    sitc = unit = rate = None
    if parts and SITC.match(parts[-1]):
        sitc = parts.pop()
    if parts and UNIT.match(parts[-1]) and not RATE.match(parts[-1]):
        unit = parts.pop()
    if parts and RATE.match(parts[-1]):
        rate = parts.pop()
    return ' '.join(parts), rate, unit, sitc


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip().rstrip(':').strip()


def _is_ancestor(parent: str, child: str) -> bool:
    """Is the (no-rate) row `parent` a heading of `child`? Codes are 8 digits; 0102.10.00 heads 0102.10.xx, 0105.10.00 heads 0105.1x.xx."""
    stripped = parent[:6].rstrip('0')
    return child != parent and len(stripped) >= 4 and child.startswith(stripped)


def parse_tariff(source: Path) -> dict:
    """Reads the Customs Act file and returns {'lines': [...], 'national': {...}, 'list_codes': [...], 'skipped': n}.

    Row assembly rules (the descriptions are vertically centred):
      * a code line with its description: the description may continue on the next lines until the rate (on the last line) or a ':' closes it;
      * a code line with NO description: the text line above it and the line below it are its description;
      * a 4-digit heading ("07.01") continues until its text ends with '.';
      * a code line only 2 spaces from its description ("0702.00.00  Tomatoes") is a heading of its own, not a child of the heading above."""
    text = source.read_text(encoding='utf-8').split('\n')
    page = -1
    in_schedule = False
    in_lists = False
    current_list = ''
    list_rows: list[tuple[str, str]] = []
    list_codes: set[str] = set()
    rows: list[dict] = []
    cur: dict | None = None
    pre: list[str] = []

    def finish():
        nonlocal cur
        if cur is not None:
            rows.append(cur)
        cur = None

    for raw in text:
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            page = int(marker.group(1))
            pre = []
            continue
        if page < 164:
            continue
        if re.match(r'^\s*LIST [ACD]\s*$', raw) and page >= 580:
            in_lists = True
        if in_lists:
            if re.match(r'^\s*LIST A\s*$', raw):
                current_list = 'A'
            elif re.match(r'^\s*LIST C\s*$', raw):
                current_list = 'C'
            elif re.match(r'^\s*LIST D\s*$', raw):
                current_list = 'D'
            if current_list in ('A', 'C'):
                list_rows.append((current_list, raw))
            list_codes.update('.'.join(found) for found in LIST_CODE.findall(raw))
            continue
        if page >= 580 or not raw.strip():
            continue
        if re.search(r'DESCRIPTION OF GOODS', raw):
            in_schedule = True
            finish()
            pre = []
            continue
        if re.match(r'^\s*CHAPTER\s+\d+', raw):
            in_schedule = False
            finish()
            pre = []
            continue
        if not in_schedule:
            continue
        match = CODE8.match(raw)
        head = HEAD4.match(raw)
        if match or head:
            finish()
            if match:
                code, rest = match.group(2), match.group(3) or ''
                gap = (match.start(3) - match.end(2)) if match.group(3) else 0
                desc, rate, unit, sitc = _split_row(rest) if rest else ('', None, None, None)
                cur = {'code': code, 'desc': desc, 'rate': rate, 'unit': unit, 'sitc': sitc, 'page': page, 'gap': gap,
                       'above': pre[-1:] if not desc else [], 'wait_below': not desc, 'kind': 'line'}
            else:
                code, rest = head.group(2), head.group(3) or ''
                cur = {'code': code, 'desc': _clean(rest), 'rate': None, 'page': page, 'above': pre[-1:] if not rest else [], 'wait_below': not rest, 'kind': 'heading'}
            pre = []
            continue
        stripped = raw.strip()
        if NOISE.match(raw) or re.fullmatch(r'\d+', stripped):
            continue
        if cur is not None and cur['kind'] == 'heading':
            if cur['wait_below']:
                cur['desc'] = _clean(' '.join(cur['above'] + [stripped]))
                cur['wait_below'] = False
                cur['above'] = []
            elif not cur['desc'].endswith('.'):
                cur['desc'] = _clean(cur['desc'] + ' ' + stripped)
            else:
                pre = (pre + [stripped])[-4:]
            continue
        if cur is not None and cur['wait_below']:
            part, rate, unit, sitc = _split_row(stripped)
            cur['desc'] = _clean(' '.join(cur['above'] + [part]))
            cur['wait_below'] = False
            cur['above'] = []
            if rate:
                cur['rate'], cur['unit'], cur['sitc'] = rate, unit, sitc
            continue
        if cur is not None and cur['rate'] is None and not cur['desc'].endswith(':'):
            part, rate, unit, sitc = _split_row(stripped)
            cur['desc'] = _clean(cur['desc'] + ' ' + part)
            if rate:
                cur['rate'], cur['unit'], cur['sitc'] = rate, unit, sitc
            continue
        pre = (pre + [stripped])[-4:]
    finish()

    lines: list[dict] = []
    seen: set[str] = set()
    stack: list[tuple[str, str]] = []  # (code, text) of the no-rate rows above
    heading4, heading_digits = '', ''
    skipped = 0
    for row in rows:
        description = _clean(row['desc'])
        if row['kind'] == 'heading':
            heading4, heading_digits = description, row['code'].replace('.', '')
            stack = []
            continue
        code = row['code']
        if not code.startswith(heading_digits):  # a row that is its own heading ("0702.00.00 Tomatoes, fresh or chilled.")
            heading4, heading_digits, stack = '', '', []
        while stack and not _is_ancestor(stack[-1][0], code):
            stack.pop()
        if row['rate'] is None:  # a parent row ("Other:", "Pure-bred breeding animals:")
            stack.append((code, description))
            continue
        if code in seen:
            skipped += 1
            continue
        seen.add(code)
        label = description or '(description not legible)'
        specific = None
        rate = row['rate']
        if rate.startswith('$') or '¢' in rate:
            specific = rate
            rate = None
        path = [heading4] if heading4 else []
        path += [text for _, text in stack if text]
        lines.append({
            'code': code,
            'hs': code.replace('.', '')[:6],
            'description': label,
            'path': ' > '.join([*path, label]),
            'rate': rate,
            'specific': specific,
            'units': row['unit'],
            'page': row['page'],
        })
    return {'lines': lines, 'national': parse_list_rows(list_rows), 'list_codes': sorted(list_codes), 'skipped': skipped}


class GrenadaCalculator(Calculator):
    name = 'Grenada'
    currency = 'XCD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.national: dict = {}
        self.list_codes: set[str] = set()
        self.loaded_at: str | None = None

    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        sources = sorted(KNOWLEDGE_BASE.glob('*renada*customs*.md'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Grenada customs duties file is not in the knowledge base (documents/knowledge_base/*Grenada customs duties*.md).')
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
        self.national = data.get('national', {})
        self.list_codes = set(data.get('list_codes', []))
        for line in data['lines']:
            override = overrides.get(line['code'])
            line['overridden'] = bool(override)
            if override and override.get('rate'):
                line.update(rate=override['rate'], specific=None)
            line['national_rate'] = None if override else self.national.get(line['code'])
            line['in_lists'] = line['code'] in self.list_codes and not line['national_rate'] and not override
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
            'source': 'Grenada Customs Act Cap. 75A — CARICOM CET (SRO 42 of 2009) + Rum/Whisky Orders (knowledge base)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the Grenada customs duties file uploaded to the knowledge base.',
            'currency': self.currency,
            'lines_with_national_rate': sum(1 for line in self.lines if line['national_rate']),
            'lines_in_unread_lists': sum(1 for line in self.lines if line['in_lists']),
            'schedule_vs_list_conflicts': sum(1 for line in self.lines if line['national_rate'] and line['rate'] and line['national_rate']['rate'] != line['rate']),
            'lines_without_rate': sum(1 for line in self.lines if not line['rate'] and not line['specific']),
        }

    def signature(self, line: dict):
        national = line.get('national_rate')
        return (higher_rate(line['rate'], national['rate']) if national else line['rate'], line['specific'])

    # ------------------------------------------------------------ lookup
    @staticmethod
    def _summary(line: dict) -> str:
        flag = ' * (national rate may differ: List A/C/D row not read)' if line['in_lists'] else ''
        national = line['national_rate']
        if national:
            used = higher_rate(line['rate'], national['rate'])
            return f"Customs duty {used} (Grenada, List {national['list']} {national['rate']}; CET {national['cet']}{'; schedule ' + line['rate'] if line['rate'] and line['rate'] != national['rate'] else ''})"
        if line['specific']:
            return f"Customs duty {line['specific']}{flag}"
        return f"Customs duty {line['rate'] or 'not legible'}{flag}"

    def _public(self, line: dict) -> dict:
        return {'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['units'], 'summary': self._summary(line), 'page': line['page'], 'status': 'review' if line['in_lists'] or not (line['rate'] or line['specific']) else 'ok'}

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
            raise ValueError(f'Tariff line {code} not found in the Grenada tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=[f"Grenada Customs Act Cap. 75A, Fifth Schedule (CET), tariff line {line['code']}, page {line['page']} of the file"],
        )
        result.notes.append('Duty is charged on the CIF value (goods + freight + insurance).')
        origin = (inputs.origin or '').strip().lower()
        caricom = origin in CARICOM
        rate_text, specific = line['rate'], line['specific']
        national = line['national_rate']
        if national:
            if national['rate'] == 'Free' or national['rate'].endswith('%'):
                rate_text, specific = higher_rate(line['rate'], national['rate']), None
                result.notes.append(f"Grenada applies {national['rate']} to this line (List {national['list']} of the CET; the CET rate is {national['cet']}); the schedule gives {line['rate'] or 'n/a'}. Rate used: {rate_text} (the higher one, if they differ).")
            else:
                result.complete = False
                result.warnings.append(f"Grenada applies a rate to this line in List {national['list']} that this calculator does not read ({national['rate']}); the schedule rate is shown and the total may be wrong.")

        if national and line['rate'] and national['rate'] != line['rate']:
            result.warnings.append(f"CONFLICT IN THE FILE: the schedule gives this line {line['rate']} (page {line['page']}) but List {national['list']} gives Grenada {national['rate']}. The HIGHER rate ({rate_text}) is used; check which one Grenada Customs collects.")
        spirit = SPIRIT_ORDERS.get(line['code'][:7])
        if caricom:
            result.notes.append(f'{inputs.origin} is a CARICOM member: goods that qualify for Community treatment (certificate of origin) enter free of the Common External Tariff.')
            result.taxes.append(Tax('Customs duty', 0.0, '0% (CARICOM origin)', 'CIF value', f"CARICOM origin: duty waived (CET rate {rate_text or specific or 'not legible'})"))
        elif specific:
            result.complete = False
            result.warnings.append(f'This line carries a specific duty written "{specific}" in the schedule, which this calculator does not compute; it is not in the total.')
        elif rate_text == 'Free':
            result.taxes.append(Tax('Customs duty', 0.0, 'Free', 'CIF value', 'free of duty'))
        elif rate_text and re.fullmatch(r'\d+(?:\.\d+)?%', rate_text):
            pct = float(rate_text.rstrip('%'))
            result.taxes.append(Tax('Customs duty', cif * pct / 100, rate_text, 'CIF value', f'{money(cif)} × {pct:g}%'))
        else:
            result.complete = False
            result.warnings.append(f"The duty rate of line {line['code']} is not legible in the file (page {line['page']}): {rate_text or 'no rate read'}. The duty is not in the total; add the rate to overrides.json in the Grenada tariff folder.")

        if spirit and not caricom:
            order_usd = inputs.quantity_units * spirit['general_xcd_per_gallon'] / XCD_PER_USD if inputs.quantity_units is not None else None
            duty_tax = next((tax for tax in result.taxes if tax.name == 'Customs duty'), None)
            used = 'the CET/List ad valorem rate'
            if order_usd is not None and duty_tax is not None and order_usd > duty_tax.amount:
                result.taxes[result.taxes.index(duty_tax)] = Tax(f"Customs duty ({spirit['name']} Order, higher than the CET rate)", order_usd, f"EC${spirit['general_xcd_per_gallon']:g} per liquid gallon", 'gallon',
                                                                 f"{inputs.quantity_units:g} gal × EC${spirit['general_xcd_per_gallon']:g} ÷ {XCD_PER_USD}")
                used = f"the {spirit['name']} Order (EC${spirit['general_xcd_per_gallon']:g} per liquid gallon)"
            elif order_usd is None:
                used = 'the CET/List ad valorem rate (enter the quantity in gallons and the higher of the two is used)'
            result.warnings.append(
                f"CONFLICT IN THE FILE: the Customs (Import Duty on {spirit['name'].title()}) Order (SRO of 1961) sets EC${spirit['general_xcd_per_gallon']:g} per liquid gallon (general) / "
                f"EC${spirit['preferential_xcd_per_gallon']:g} (preferential), while the CET schedule and List C give Grenada an ad valorem rate for this line. "
                f'The HIGHER duty is used: {used}. Check with Grenada Customs which one is collected.'
            )
        if line['in_lists'] and not caricom:
            result.warnings.append('This line appears in a List A/C/D row of the CET (where Grenada may apply a rate different from the CET) that could not be read. The schedule rate is shown — verify it.')
        if origin in EPA_ORIGINS:
            result.warnings.append(f'{inputs.origin} is an EPA partner, but the Economic Partnership Agreement Tariff Orders listed in the file index are not in the file: the normal rate is shown, which may be higher than the preferential EPA rate.')
        elif inputs.origin and not caricom:
            result.notes.append(f'No origin preference is applied for {inputs.origin}: the standard CET rate applies.')

        duty = sum(tax.amount for tax in result.taxes)
        result.taxes.append(
            Tax('Value added tax (VAT)', (cif + duty) * VAT_RATE, '15%', 'CIF value + duty', f'({money(cif)} + {money(duty)}) × 15%', recoverable=True,
                note='Not counted: a VAT-registered importer credits it, and basic foods may be zero-rated. VAT is not in the uploaded file — the 15% rate comes from public sources, verify it.')
        )
        result.warnings.append('Not included: customs service charge and other fees, excise, duty exemptions granted for approved purposes (Conditional Duty Exemptions), import licences and sanitary/phytosanitary permits. The CET in the file is the HS 2007 edition (in force 1 Feb 2010); a current product code may not exist in it.')
        return result
