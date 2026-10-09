"""Saint Lucia: import duty from the CARICOM Common External Tariff, 2012 edition ("saint lucia customs duties" in the knowledge base).

The file is a text extraction of the printed CET: columns HS | CET | DESCRIPTION OF GOODS | DUTY RATE | EPA 2011-2033 | UNIT | SITC.
`refresh()` turns the schedule pages into `documents/tax_data/Saint Lucia/tariff.json` (one record per 8-digit line, e.g. 0207.14.20) and
reads the EPA phase-down table (codes 1-A … 26-A, tariff on 1 January of each year to 2033).

Rules applied (see the notes on every result):
  * duty on the CIF value; ad valorem (n%), specific ($1.65 per 100 kg, in EC dollars, pegged at 2.70 per US$) or Free;
  * CARICOM origin: goods that qualify for Community treatment enter free of the CET (this edition says so on its general-note page);
  * EU origin (the CARIFORUM–EU EPA): the line's EPA column — "Free" stays free, "Excl" (sensitive) keeps the CET rate, a code like "3-B"
    is looked up in the phase-down table for the current year;
  * VAT 12.5% on CIF + duty is shown but not counted (registered importers credit it; about 70 staple foods are zero-rated — that list is
    not in this file).
Lists A and C (the rates each member state applies where they differ from the CET) are read from a re-extracted copy of pages 599-627 that
was spliced into the knowledge-base file: the Saint Lucia column (11th of CET + 13 states) overrides the schedule rate when present; every
parsed value agrees with the schedule's own printed rate. List D (pages 628-635) and the few List A/C rows whose values did not parse cleanly
are NOT loaded: lines whose code appears in them carry a warning. This is the 2012 edition (HS 2007 codes); Saint Lucia now uses HS 2017 codes.

Files next to the tariff (optional, survive a refresh): overrides.json {"0201.10.00": {"rate": "40%"}} — hand corrections, e.g. a national
rate read from List A/C/D or the current gazette.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, money, query_words, rank
from .jamaica import CARICOM

FOLDER = DATA_ROOT / 'Saint Lucia'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
XCD_PER_USD = 2.70  # EC dollar, fixed peg
VAT_RATE = 0.125
EPA_ORIGINS = {
    'austria', 'belgium', 'bulgaria', 'croatia', 'cyprus', 'czechia', 'czech republic', 'denmark', 'estonia', 'finland', 'france', 'germany',
    'greece', 'hungary', 'ireland', 'italy', 'latvia', 'lithuania', 'luxembourg', 'malta', 'netherlands', 'poland', 'portugal', 'romania',
    'slovakia', 'slovenia', 'spain', 'sweden',
}

CODE = re.compile(r'^(\s+)(\d{4}\.\d{2}|\d{2}\.\d{2})\s{2,}(?:(\d{2}(?:\s+\d{2})?)\s{2,})?(\S.*)$')
RATE = re.compile(r'^(?:Free|\d+(?:\.\d+)?%|\$\s?[\d.,]+)$')
EPA_CODE = re.compile(r'^\d{1,2}-[A-K]$')
NOISE = re.compile(r'^\s*(?:EPA\b|HS\s|DUTY|RATE|per\s+\d+|kg\s*$|\d+\s*$|```|>|SITC|UNIT|REV)', re.IGNORECASE)


def _depth(text: str) -> int:
    return len(re.match(r'[\s\-–—]*', text).group(0).replace(' ', ''))


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^[\s\-–—]+', '', text)).strip().rstrip(':').strip()


LIST_TOKEN = re.compile(r'\d+(?:\.\d+)?%/\s*\d+(?:\.\d+)?%|\d+(?:\.\d+)?%/|\d+¢|\$\s?\d[\d.,]*(?:\s+per\s+(?:Imp\.\s+)?(?:litre|L\.?\s?gal\.?|gal\.?|head|kg|100\s?kg))?|Free|\d+(?:\.\d+)?%')
LIST_CODE = re.compile(r'(\d{4})\s?\.\s?(\d{2})\s?\.\s?(\d{2})')
SAINT_LUCIA_COLUMN = 10  # CET, ANT&BAR, BDS, BEL, DOM, GREN, GUY, JAM, MONT, K&N, SAINT LUCIA, V&G, SUR, T&T (Lists A and C)


def _list_tokens(line: str) -> list[str]:
    line = re.sub(r'F\s+r\s*e\s*e', 'Free', line)  # OCR split "F  ree"
    line = re.sub(r'(?<![\d.$])(\d)\s+(\d{1,2}%)', lambda m: m.group(1) + m.group(2), line)  # "3  0%" -> "30%", "1  00%" -> "100%"
    line = re.sub(r'(\d+%)\s*/\s*(\d+%)', lambda m: m.group(1) + '/' + m.group(2), line)  # "30%/ 35%" is one value
    line = re.sub(r'\$\s+(\d)', lambda m: '$' + m.group(1), line)
    tokens = [token.strip() for token in LIST_TOKEN.findall(line)]
    return tokens[-14:] if len(tokens) > 14 else tokens  # the values end the row; "1%" / "6%" in a wrapped description come before them


def parse_list_rows(lines: list[tuple[str, str]]) -> dict:
    """[(list letter, line)] of Lists A and C -> {code: {'rate': Saint Lucia's rate, 'list': 'A', 'cet': the list's CET rate}}.
    A row is read only when it carries all 14 values (CET + 13 states); a row whose values wrap onto the next line is completed from it."""
    national: dict = {}
    pending: tuple[str, str] | None = None
    for letter, line in lines:
        codes = LIST_CODE.findall(line)
        tokens = _list_tokens(line)
        if codes:
            code = '.'.join(codes[-1])
            if len(tokens) == 14:
                national[code] = {'rate': tokens[SAINT_LUCIA_COLUMN], 'list': letter, 'cet': tokens[0]}
                pending = None
            else:
                pending = (code, letter)
        elif pending and len(tokens) == 14:
            national[pending[0]] = {'rate': tokens[SAINT_LUCIA_COLUMN], 'list': pending[1], 'cet': tokens[0]}
            pending = None
    return national


def parse_epa_table(lines: list[str]) -> dict:
    """{'3-B': {2013: 5.0, 2015: 5.0, …}} from the 'EPA Tariff on 1st January' tables (values in %, 0 for Free)."""
    table: dict = {}
    years: list[int] = []
    for raw in lines:
        if raw.strip().startswith('Code') and '2013' in raw:
            years = [int(year) for year in re.findall(r'\b(20\d\d)\b', raw)]
            continue
        match = re.match(r'^\s*(\d{1,2}-[A-K])\s+((?:(?:Free|\d+)\s+){3,}(?:Free|\d+))\s*$', raw)
        if match and years:
            values = match.group(2).split()
            if len(values) == len(years):
                table[match.group(1)] = {year: (0.0 if value == 'Free' else float(value)) for year, value in zip(years, values)}
    return table


def parse_tariff(source: Path) -> dict:
    """Reads the printed CET and returns {'lines': [...], 'epa': {...}, 'list_codes': [...], 'skipped': n}."""
    text = source.read_text(encoding='utf-8').split('\n')
    lines: list[dict] = []
    seen: set[str] = set()
    stack: list[tuple[int, str]] = []
    skipped = 0
    page = 0
    last: dict | None = None
    in_table = False
    in_lists = False
    list_codes: set[str] = set()
    epa_lines: list[str] = []
    list_rows: list[tuple[str, str]] = []
    current_list = ''

    for raw in text:
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            page, last, in_table = int(marker.group(1)), None, False
            continue
        if page >= 500 and 'LIST A' in raw and 'ITEMS ON WHICH' in raw.upper() or (page >= 500 and re.match(r'^\s*LIST [ACD]\b', raw)):
            in_lists = True
        if in_lists:
            if re.search(r'LIST A\b', raw):
                current_list = 'A'
            elif re.search(r'LIST C\b|MINIMUM RATES\s+HAVE BEEN AGREED', raw):
                current_list = 'C'
            elif re.search(r'LIST D\b', raw):
                current_list = 'D'
            if current_list in ('A', 'C'):
                list_rows.append((current_list, raw))
            list_codes.update('.'.join(found) for found in LIST_CODE.findall(raw))
            continue
        if 30 <= page <= 40:
            epa_lines.append(raw)
        if 'DESCRIPTION OF GOODS' in raw:
            in_table = True
            continue
        if not in_table or page < 37 or not raw.strip():
            continue
        match = CODE.match(raw)
        if match:
            code, cet, rest = match.group(2), (match.group(3) or '').split(), match.group(4)
            indent = match.start(4)
            parts = re.split(r'\s{2,}', rest.strip())
            rate_at = next((i for i, part in enumerate(parts) if RATE.match(part.strip())), None)
            if rate_at is None or len(code) == 5:  # a heading row (07.03 …) or a sub-heading with no rate
                description = ' '.join(parts)
                depth = 0 if len(code) == 5 else _depth(description)
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                stack.append((depth, description))
                last = {'heading': True, 'indent': indent, 'pos': len(stack) - 1}
                continue
            description = ' '.join(parts[:rate_at])
            rate = parts[rate_at].strip()
            after = [part.strip() for part in parts[rate_at + 1:]]
            epa = next((p for p in after if p in ('Free', 'Excl', 'n.a.') or EPA_CODE.match(p)), None)
            unit = next((p for p in after if re.match(r'^(?:kg|Kg|l\b|u\b|m\b)', p)), None)
            record = {'hs': code, 'cet': cet, 'description': description, 'rate': rate, 'epa': epa, 'unit': unit, 'page': page, 'depth': _depth(description), 'stack': list(stack), 'indent': indent}
            last = record
            lines.append(record)
            continue
        # text with no code: a dash sub-heading, or the wrapped end of the row above
        stripped = raw.strip()
        if NOISE.match(raw):
            continue
        indent = len(raw) - len(raw.lstrip())
        if last is None or not -3 <= indent - last['indent'] <= 12:
            continue
        if stripped.startswith('-'):
            depth = _depth(stripped)
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, stripped))
            last = {'heading': True, 'indent': last['indent'], 'pos': len(stack) - 1}
        elif last.get('heading'):
            if last['pos'] < len(stack):
                stack[last['pos']] = (stack[last['pos']][0], stack[last['pos']][1] + ' ' + stripped)
        else:
            last['description'] += ' ' + stripped

    out = []
    for record in lines:
        cets = record['cet'] or ['00']
        for index, cet in enumerate(cets):
            code = f"{record['hs']}.{cet}"
            if code in seen:
                skipped += 1
                continue
            seen.add(code)
            label = _clean(record['description']) or '(description not legible)'
            path = [_clean(item) for d, item in record['stack'] if d < record['depth'] and _clean(item)]
            rate = record['rate']
            specific = None
            if rate.startswith('$'):
                specific = float(re.sub(r'[^\d.]', '', rate))
            out.append({
                'code': code,
                'hs': record['hs'].replace('.', ''),
                'description': label,
                'path': ' > '.join([*path, label]),
                'rate': None if specific else rate,
                'specific_xcd_per_100kg': specific,
                'epa': record['epa'],
                'units': record['unit'],
                'page': record['page'],
            })
    normalized = set(list_codes)
    return {'lines': out, 'epa': parse_epa_table(epa_lines), 'list_codes': sorted(normalized), 'national': parse_list_rows(list_rows), 'skipped': skipped}


class SaintLuciaCalculator(Calculator):
    name = 'Saint Lucia'
    currency = 'XCD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.epa: dict = {}
        self.list_codes: set[str] = set()
        self.national: dict = {}
        self.loaded_at: str | None = None

    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        sources = sorted(KNOWLEDGE_BASE.glob('*aint*ucia*customs*.md'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Saint Lucia customs tariff is not in the knowledge base (documents/knowledge_base/*saint lucia customs duties*.md).')
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
        self.epa = {code: {int(year): value for year, value in years.items()} for code, years in data.get('epa', {}).items()}
        self.list_codes = set(data.get('list_codes', []))
        self.national = data.get('national', {})
        for line in data['lines']:
            override = overrides.get(line['code'])
            line['national'] = bool(override)
            if override and override.get('rate'):
                line.update(rate=override['rate'], specific_xcd_per_100kg=None)
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
            'source': 'CARICOM Common External Tariff 2012 — Saint Lucia (knowledge base)',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the Saint Lucia customs tariff uploaded to the knowledge base.',
            'currency': self.currency,
            'lines_with_national_rate': sum(1 for line in self.lines if line['national_rate']),
            'lines_in_unread_lists': sum(1 for line in self.lines if line['in_lists']),
            'epa_codes': len(self.epa),
        }

    def signature(self, line: dict):
        national = line.get('national_rate')
        return (national['rate'] if national else line['rate'], line['specific_xcd_per_100kg'])

    # ------------------------------------------------------------ lookup
    @staticmethod
    def _summary(line: dict) -> str:
        flag = ' * (national rate may differ: List A/C/D not read)' if line['in_lists'] else ''
        national = line['national_rate']
        if national:
            return f"Customs duty {national['rate']} (Saint Lucia, List {national['list']}; CET {national['cet']})"
        if line['specific_xcd_per_100kg']:
            return f"Customs duty EC${line['specific_xcd_per_100kg']:g} per 100 kg{flag}"
        return f"Customs duty {line['rate'] or 'not legible'}{flag}"

    def _public(self, line: dict) -> dict:
        return {'code': line['code'], 'description': line['description'], 'path': line['path'], 'units': line['units'], 'summary': self._summary(line), 'page': line['page'], 'status': 'review' if line['in_lists'] else 'ok'}

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
    def _epa_rate(self, line: dict, year: int) -> tuple[float | None, str]:
        """(rate in %, explanation) of the EPA column for this year, or (None, reason) when the CET rate stays."""
        epa = line['epa']
        if epa == 'Free':
            return 0.0, 'EPA: free of duty for EU-origin goods'
        if epa == 'Excl':
            return None, 'EPA: this line is excluded (sensitive), the applied rate (the rate Saint Lucia applies) applies'
        if epa and epa in self.epa:
            by_year = self.epa[epa]
            applicable = max((y for y in by_year if y <= year), default=None)
            if applicable is None:
                return None, f'EPA code {epa} has no cut yet'
            return by_year[applicable], f'EPA code {epa}: {by_year[applicable]:g}% on 1 January {applicable} (phase-down table)'
        return None, f'EPA code {epa or "—"} could not be read; the CET rate is shown'

    def calculate(self, code: str, inputs: Inputs) -> Result:
        self._ensure()
        line = self.by_code.get((code or '').strip()) or self.by_code.get(digits(code))
        if line is None:
            raise ValueError(f'Tariff line {code} not found in the Saint Lucia tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=[f"CARICOM Common External Tariff 2012 (Saint Lucia copy), tariff line {line['code']}, page {line['page']}"],
        )
        result.notes.append('Duty is charged on the CIF value (goods + freight + insurance).')
        origin = (inputs.origin or '').strip().lower()
        caricom = origin in CARICOM
        epa_rate, epa_note = (None, '')
        if origin in EPA_ORIGINS:
            epa_rate, epa_note = self._epa_rate(line, date.today().year)
            result.notes.append(epa_note + '.')

        rate_text, specific = line['rate'], line['specific_xcd_per_100kg']
        national = line['national_rate']
        if national:
            if national['rate'] == 'Free' or national['rate'].endswith('%'):
                rate_text, specific = national['rate'], None
                result.notes.append(f"Saint Lucia applies {national['rate']} to this line (List {national['list']} of the CET; the CET rate is {national['cet']}).")
            else:
                result.complete = False
                result.warnings.append(f"Saint Lucia applies a specific rate to this line in List {national['list']} ({national['rate']}); this calculator does not read it, so the CET rate is shown and the total may be wrong.")

        if caricom:
            result.notes.append(f'{inputs.origin} is a CARICOM member: goods that qualify for Community treatment (certificate of origin) enter free of the Common External Tariff.')
            result.taxes.append(Tax('Customs duty', 0.0, '0% (CARICOM origin)', 'CIF value', f"CARICOM origin: duty waived (CET rate {rate_text or 'EC$%g per 100 kg' % (specific or 0)})"))
        elif epa_rate is not None:
            result.taxes.append(Tax('Customs duty (EPA)', cif * epa_rate / 100, f'{epa_rate:g}%' if epa_rate else 'Free', 'CIF value', f'{money(cif)} × {epa_rate:g}%' if epa_rate else 'free of duty (EPA)'))
        elif specific:
            per = specific / XCD_PER_USD
            if inputs.quantity_kg is None:
                result.complete = False
                result.warnings.append(f"The duty is EC${specific:g} per 100 kg: enter the quantity in kg to include it in the total.")
            else:
                result.taxes.append(Tax('Customs duty (specific)', inputs.quantity_kg / 100 * per, f"EC${specific:g} per 100 kg", 'kg', f"{inputs.quantity_kg:g} kg ÷ 100 × EC${specific:g} ÷ {XCD_PER_USD}"))
                result.notes.append(f'Specific duties are written in EC dollars and converted at EC$ {XCD_PER_USD} per US$ (fixed peg).')
        elif rate_text == 'Free':
            result.taxes.append(Tax('Customs duty', 0.0, 'Free', 'CIF value', 'free of duty'))
        elif rate_text and rate_text.endswith('%'):
            pct = float(rate_text.rstrip('%'))
            result.taxes.append(Tax('Customs duty', cif * pct / 100, rate_text, 'CIF value', f'{money(cif)} × {pct:g}%'))
        else:
            result.complete = False
            result.warnings.append(f"The duty rate of line {line['code']} could not be read (page {line['page']}); the duty is not in the total.")

        if line['in_lists'] and not caricom:
            result.warnings.append('This line appears in List D of the CET (items where Saint Lucia applies a rate different from the CET) or in a List A/C row that could not be read. Those rows are not loaded: the CET rate is shown, which may differ from the rate Saint Lucia actually charges — verify it, and add the national rate to overrides.json.')
        if line['national']:
            result.notes.append('The rate was corrected by hand (overrides.json).')
        if inputs.origin and not caricom and origin not in EPA_ORIGINS:
            result.notes.append(f'No origin preference is applied for {inputs.origin}: the standard CET rate applies.')

        duty = sum(tax.amount for tax in result.taxes)
        result.taxes.append(
            Tax('Value added tax (VAT)', (cif + duty) * VAT_RATE, '12.5%', 'CIF value + duty', f'({money(cif)} + {money(duty)}) × 12.5%', recoverable=True,
                note='Not counted: a VAT-registered importer credits it, and about 70 staple foods are zero-rated (that list is not in this tariff — check the product).')
        )
        result.warnings.append('Not included: Customs Service Charge and other port/customs fees, excise tax (fuel, liquor, beer, cigarettes), duty exemptions granted for approved purposes, import licences and sanitary/phytosanitary permits. This is the 2012 edition of the CET (HS 2007 codes); Saint Lucia now uses HS 2017 codes, so the code of a current product may not exist here.')
        return result
