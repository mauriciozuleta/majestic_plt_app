"""Barbados: import duty, inspection fee, excise and VAT from the Barbados Customs Tariff ("Barbados customs duties" in the knowledge base:
Customs Tariff (Amendment) Order 2019, S.I. 2019 No. 57, replacing Parts I and II of the Customs Tariff with the revised CET, HS 2017, 11 April 2018).

File layout (page = the file's `page-N` marker; see BARBADOS_RULES.md):
  pp. 1-3      the Amendment Order: Section B goods pay 60% "notwithstanding" Section A; the Special Safeguard formula for Section C goods
  pp. 46-633   Part 1 Section A, the national schedule: HS | CET | description | DUTY RATE | [INSPECTION FEE or EXCISE RATE (or FUEL TAX)] | VAT RATE | UNIT | SITC
  pp. 636-642  Part 1 Section B: goods charged 60% whatever Section A says ("ex" = only part of the heading, with exclusions)
  pp. 643-652  Part 1 Section C: goods with a Special Safeguard trigger price per kg (1986-88 reference period)
  pp. 653-718  conditional duty exemptions and the commodities ineligible for them
  pp. 719-1053 "EPA rates until 2020"
  pp. 1055-1096 CET Lists A, C, D (the Barbados column is the 3rd value: CET, ANT&BAR, BARBADOS, BEL …)

`refresh()` writes `documents/tax_data/Barbados/tariff.json` (one record per line, e.g. 0207.14.20.000) plus the Section B/C tables.

Rules applied (see the notes on every result): duty on the CIF value; CARICOM origin = free; Section B goods 60%; Section C goods may owe the Special Safeguard
additional duty (computed per kg from the trigger price, assuming no quota allocation); inspection fees per head/batch need the quantity; excise (n%) is charged
on CIF + duty (assumption: the file gives no base); VAT uses the rate printed on the line (17.5% or 0%) on CIF + duty + excise and is shown, not counted
(a VAT-registered importer credits it). EPA preferential rates ("until 2020") are not applied. BBD is pegged at 2 per US$.

Hand corrections: `overrides.json` next to the tariff, {"0201.10.00.000": {"duty": "30%"}}.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .base import DATA_ROOT, Calculator, Inputs, Result, Tax, digits, higher_rate, money, query_words, rank
from .jamaica import CARICOM

FOLDER = DATA_ROOT / 'Barbados'
KNOWLEDGE_BASE = Path(__file__).resolve().parent.parent / 'documents' / 'knowledge_base'
BBD_PER_USD = 2.0
SECTION_A_PAGES = range(46, 634)
SECTION_B_PAGES = range(636, 643)
SECTION_C_PAGES = range(643, 653)
LISTS_PAGES = range(1055, 1100)
BARBADOS_COLUMN = 2  # CET, ANT&BAR, BARBADOS, BEL, DOM, GREN, GUY, JAM, MONT, K&N, LUCIA, V&G, SUR, T&T
EPA_ORIGINS = {
    'austria', 'belgium', 'bulgaria', 'croatia', 'cyprus', 'czechia', 'czech republic', 'denmark', 'estonia', 'finland', 'france', 'germany',
    'greece', 'hungary', 'ireland', 'italy', 'latvia', 'lithuania', 'luxembourg', 'malta', 'netherlands', 'poland', 'portugal', 'romania',
    'slovakia', 'slovenia', 'spain', 'sweden',
}

CODE = re.compile(r'^\s*(\d{4})\s?\.\s?(\d{2})\s+(\d{2})\s?\.\s?(\d{3})(?:\s{1,}(.*))?$')  # 0201.10  00.000  desc ...
PARENT = re.compile(r'^\s*(\d{4})\s?\.\s?(\d{2})\s+(\d{2})(?:\s{2,}(.*))?$')  # 0101.29  00  - - Other:
HEADING = re.compile(r'^\s*(\d{2})\.(\d{2})(?:\s{2,}(.*))?$')  # 01.01  Live horses ...
PERCENT = re.compile(r'^(?:Free|\d+(?:\.\d+)?%)$')
SPECIFIC = re.compile(r'^\$\s?\d[\d.,]*(?:\s*(?:each|per\b.*))?')
SITC = re.compile(r'^\d{3}\.\d+(?:\([A-Z]\))?$')
UNIT = re.compile(r'^(?:[Kk]g|kilo|2\s?u|u|l|m2|m3)\b.*$')
VAT_VALUES = {'17.5%', '17.50%', '0%', '0.0%', '0.00%'}
NOISE = re.compile(r'^\s*(?:HS\b|CET\b|DESCRIPTION|DUTY|EXCISE|VAT|RATE|FUEL|INSPECTION|FEE|UNIT|SITC|REV|L\.R\.O|THE LAWS|Printed by|by the authority|CHAPTER\b|Note|Notes|```|>|\d{1,4}\s*$)', re.IGNORECASE)

LIST_TOKEN = re.compile(r'\d+(?:\.\d+)?%/\s*\d+(?:\.\d+)?%|\d+(?:\.\d+)?%/|\d+(?:\.\d+)?¢|\$\s?\d[\d.,]*(?:\s+per\s+(?:Imp\.\s+)?(?:litre|L\.?\s?gal\.?|gal\.?|head|kg|100\s?kg))?|Free|\d+(?:\.\d+)?%')
LIST_CODE = re.compile(r'(\d{4})\s?\.\s?(\d{2})\s?\.\s?(\d{2})')


def _depth(text: str) -> int:
    return len(re.match(r'[\s\-–—]*', text).group(0).replace(' ', ''))


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'^[\s\-–—]+', '', text)).strip().rstrip(':').strip()


def _pages(source: Path) -> dict[int, list[str]]:
    pages: dict[int, list[str]] = {}
    page = -1
    for raw in source.read_text(encoding='utf-8').split('\n'):
        marker = re.match(r'## page-(\d+)', raw)
        if marker:
            page = int(marker.group(1))
            pages[page] = []
        elif page >= 0:
            pages[page].append(raw)
    return pages


# ------------------------------------------------------------------ Section A
def _split_tail(parts: list[str]) -> dict:
    """The cells after the description: duty, optional inspection fee / excise, VAT, unit, SITC. `parts` are the 2+-space separated pieces of the line."""
    parts = [part.strip() for part in parts if part.strip()]
    out = {'duty': None, 'extra': None, 'vat': None, 'unit': None, 'sitc': None, 'description': []}
    if parts and SITC.match(parts[-1]):
        out['sitc'] = parts.pop()
    if parts and UNIT.match(parts[-1]) and not PERCENT.match(parts[-1]):
        out['unit'] = parts.pop()
    # the first rate-like piece starts the rate cells; everything before it is description
    first = next((i for i, part in enumerate(parts) if PERCENT.match(part) or SPECIFIC.match(part) or part in ('ex T&T', 'kilo')), None)
    if first is None:
        out['description'] = parts
        return out
    out['description'] = parts[:first]
    cells = [part for part in parts[first:] if part != 'kilo']
    percents = [i for i, part in enumerate(cells) if PERCENT.match(part)]
    vat_at = next((i for i in reversed(percents) if cells[i] in VAT_VALUES), None)
    if vat_at is not None:
        out['vat'] = cells[vat_at]
        cells = cells[:vat_at] + cells[vat_at + 1:]
    if cells:
        out['duty'] = cells[0]
    if len(cells) > 1:
        out['extra'] = ' '.join(cells[1:])
    return out


def _middle_column(page_lines: list[str]) -> str | None:
    """What the optional cell between DUTY and VAT means on this page, from the table header: inspection fee, countervailing duty or excise."""
    header = ' '.join(line.strip() for line in page_lines[:14]).upper()
    if 'COUNTER' in header:
        return 'countervailing'
    if 'INSPECTION' in header:
        return 'inspection'
    if 'EXCISE' in header:
        return 'excise'
    return None


def parse_section_a(pages: dict[int, list[str]]) -> tuple[list[dict], int]:
    rows: list[dict] = []
    stack: list[tuple[int, str]] = []  # (dash depth, text) of the no-rate rows / sub-headings above
    heading = ''
    heading_code = ''
    heading_open = False  # the 4-digit heading's text may continue on the next lines until it ends with '.'
    cur: dict | None = None
    buffer: list[str] = []  # specific amounts written on their own line ($44.09 per kg ...), for the next row that has no rate of its own
    skipped = 0

    def finish():
        nonlocal cur
        if cur is not None:
            rows.append(cur)
        cur = None

    column = None
    for page in SECTION_A_PAGES:
        column = _middle_column(pages.get(page, [])) or column
        for raw in pages.get(page, []):
            if not raw.strip():
                continue
            code = CODE.match(raw)
            parent = PARENT.match(raw)
            head = HEADING.match(raw)
            if code:
                finish()
                heading_open = False
                hs6 = f'{code.group(1)}.{code.group(2)}'
                tail = _split_tail(re.split(r'\s{2,}', (code.group(5) or '').strip()))
                description = ' '.join(tail['description'])
                cur = {'code': f'{hs6}.{code.group(3)}.{code.group(4)}', 'page': page, 'tail': tail, 'description': description, 'depth': _depth(description), 'stack': list(stack),
                       'heading': heading if f'{code.group(1)}'.startswith(heading_code) else '', 'column': column,
                       'specific_text': ' '.join(buffer) if tail['duty'] is None and column != 'countervailing' else '',
                       'fee_text': ' '.join(buffer) if column == 'countervailing' else ''}
                buffer = []
                continue
            if parent:
                finish()
                heading_open = False
                text = parent.group(4) or ''
                depth = _depth(text)
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                stack.append((depth, text))
                buffer = []
                continue
            if head and not code:
                finish()
                heading = (head.group(3) or '').strip()
                heading_code = f'{head.group(1)}{head.group(2)}'
                heading_open = not heading.endswith('.')
                stack = []
                buffer = []
                continue
            if NOISE.match(raw):
                continue
            text = raw.strip()
            is_amount = bool(re.match(r'^\$\s?\d', text) or re.match(r'^batch', text) or re.match(r'^ex\s*T&T\s*$', text) or re.fullmatch(r'(?:per\s?\S*\s*)+(?:of\s+alcohol)?', text))
            if is_amount:
                if cur is not None and cur['tail']['duty'] is not None:
                    cur['fee_text'] = (cur['fee_text'] + ' ' + text).strip()  # fee wrapped under its row ("batch =< 3 / $35.00 > 3")
                elif cur is not None and cur['tail']['duty'] is None and cur['tail']['vat'] is None:
                    cur['specific_text'] = (cur['specific_text'] + ' ' + text).strip()
                else:
                    buffer.append(text)
                continue
            if cur is not None and cur['tail']['duty'] is None and cur['tail']['vat'] is None:  # a row whose rates sit on a later line
                tail = _split_tail(re.split(r'\s{2,}', text))
                cur['description'] = (cur['description'] + ' ' + ' '.join(tail['description'])).strip()
                for key in ('duty', 'extra', 'vat', 'unit', 'sitc'):
                    if tail[key] and not cur['tail'][key]:
                        cur['tail'][key] = tail[key]
                continue
            if cur is not None:
                cur['description'] = (cur['description'] + ' ' + text).strip() if not text.startswith('-') else cur['description']
                if text.startswith('-'):  # an un-coded sub-heading ("- Of fowls of the species ...:") for the rows after it
                    finish()
                    depth = _depth(text)
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    stack.append((depth, text))
                continue
            if text.startswith('-'):
                depth = _depth(text)
                while stack and stack[-1][0] >= depth:
                    stack.pop()
                stack.append((depth, text))
                heading_open = False
            elif heading_open:
                heading = (heading + ' ' + text).strip()
                heading_open = not heading.endswith('.')
    finish()

    lines: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        tail = row['tail']
        if tail['duty'] is None and not row['specific_text']:
            skipped += 1
            continue
        if row['code'] in seen:
            skipped += 1
            continue
        seen.add(row['code'])
        label = _clean(row['description']) or '(description not legible)'
        path = [row['heading']] if row['heading'] else []
        path += [_clean(text) for depth, text in row['stack'] if depth < row['depth'] and _clean(text)]
        duty, extra = tail['duty'], tail['extra']
        specific = None
        if duty is not None and not PERCENT.match(duty):
            duty, specific = None, duty
        status, note = 'ok', ''
        if duty is None:
            status, note = 'review', 'the duty is a specific amount or could not be read: ' + (specific or row['specific_text'] or 'n/a')
        charge = ' '.join(dict.fromkeys(part for part in (extra, row['fee_text'], row['specific_text'] if duty is not None else '') if part)).strip() 
        charge = re.sub(r'(\$[\d.]+ per l)(?:\s+\1)+', r'\1', charge) or None
        extra_kind = None
        if row['column'] == 'countervailing':
            extra_kind = 'countervailing' if charge and ('$' in charge or 'T&T' in charge) else None
        elif row['column'] == 'inspection':
            extra_kind = 'inspection' if charge else None
        elif extra and row['column'] == 'excise':
            extra_kind = 'excise_pct' if PERCENT.match(extra) else 'excise_specific'
        elif extra:
            extra_kind = 'excise_pct' if PERCENT.match(extra) else 'other'
        fee = charge if extra_kind in ('inspection', 'countervailing', 'excise_specific', 'other') else None
        lines.append({
            'code': row['code'], 'hs': digits(row['code'])[:6], 'description': label, 'path': ' > '.join([*path, label]) if path else label, 'duty': duty, 'duty_specific': specific,
            'extra': extra, 'extra_kind': extra_kind, 'inspection_fee': fee, 'column': row['column'], 'vat': tail['vat'], 'units': tail['unit'], 'specific_text': row['specific_text'] or None,
            'page': row['page'], 'status': status, 'note': note,
        })
    return lines, skipped


# ------------------------------------------------------------------ Sections B and C
def parse_section_b(pages: dict[int, list[str]]) -> list[dict]:
    """Goods charged 60%: [{code (digits), raw, ex, text}]. 'ex' = only part of the heading is covered (the exclusions are in the text)."""
    entries: list[dict] = []
    for page in SECTION_B_PAGES:
        last: dict | None = None
        for raw in pages.get(page, []):
            match = re.match(r'^\s*(ex\s+)?(\d{2}\.\d{2}(?:\.\d{2}){0,2}|\d{4}\.\d{2}(?:\.\d{2}){0,2}|\d{4}\.\d{2})\s+(.*)$', raw)
            if match:
                text = re.sub(r'\s*60%\s*$', '', match.group(3)).strip()
                last = {'code': digits(match.group(2)), 'raw': match.group(2), 'ex': bool(match.group(1)), 'text': text}
                entries.append(last)
            elif last is not None and raw.strip() and not NOISE.match(raw) and not re.match(r'^(Tariff|Description|Heading|Duty|Rate of)\b', raw.strip()):
                last['text'] = (last['text'] + ' ' + re.sub(r'\s*60%\s*$', '', raw.strip())).strip()
    return [entry for entry in entries if len(entry['code']) >= 4]


def parse_section_c(pages: dict[int, list[str]]) -> dict[str, dict]:
    """Special Safeguard trigger prices (BBD per kg, 1986-88 reference period): {digits of the code: {'code', 'trigger_bbd_per_kg', 'text'}}."""
    prices: dict[str, dict] = {}
    pending: list[tuple[str, str]] = []  # (code, text) seen without a price yet
    for page in SECTION_C_PAGES:
        for raw in pages.get(page, []):
            match = re.match(r'^\s*(?:ex\s+)?(\d{4}\.\d{2}\.\d{2}(?:\.\d{2})?)\s+(.*)$', raw)
            price = re.search(r'\$\s?(\d+(?:\.\d+)?)\s*$', raw)
            if match:
                code, text = match.group(1), re.sub(r'\s*\$\s?\d+(?:\.\d+)?\s*$', '', match.group(2)).strip()
                if price:
                    prices[digits(code)] = {'code': code, 'trigger_bbd_per_kg': float(price.group(1)), 'text': text}
                elif not raw.strip().startswith('ex'):
                    pending.append((code, text))
            elif price and pending and not NOISE.match(raw):
                code, text = pending.pop()
                prices[digits(code)] = {'code': code, 'trigger_bbd_per_kg': float(price.group(1)), 'text': text}
    return prices


def safeguard_additional_duty(trigger: float, import_price: float) -> float:
    """BBD per kg of additional duty (S.I. 2019 No. 57, s.4(2)) from the trigger price and the c.i.f. import price per kg, both in BBD.
    difference = trigger - price; r = difference / trigger. r <= 10%: none; 10-40%: 30% of the amount by which the difference exceeds 10%; 40-60%: + 50% of the
    excess over 40%; 60-75%: + 70% of the excess over 60%; above 75%: + 90% of the excess over 75%."""
    if trigger <= 0 or import_price >= trigger:
        return 0.0
    ratio = (trigger - import_price) / trigger
    tiers = ((0.10, 0.40, 0.30), (0.40, 0.60, 0.50), (0.60, 0.75, 0.70), (0.75, 1.0, 0.90))
    total = sum(share * (min(ratio, high) - low) for low, high, share in tiers if ratio > low)
    return trigger * total


# ------------------------------------------------------------------ Lists A / C (cross-check only)
def _list_tokens(line: str) -> list[str]:
    line = re.sub(r'F\s+r\s*e\s*e', 'Free', line)
    line = re.sub(r'(?<![\d.$])(\d)\s+(\d{1,2}%)', lambda m: m.group(1) + m.group(2), line)
    line = re.sub(r'(\d+%)\s*/\s*(\d+%)', lambda m: m.group(1) + '/' + m.group(2), line)
    line = re.sub(r'\$\s+(\d)', lambda m: '$' + m.group(1), line)
    tokens = [token.strip() for token in LIST_TOKEN.findall(line)]
    return tokens[-14:] if len(tokens) > 14 else tokens


def parse_list_rows(pages: dict[int, list[str]]) -> dict:
    """{code (8 digits with dots): {'rate': Barbados' rate, 'list': 'A'|'C', 'cet': the CET rate}} from rows that carry all 14 values."""
    national: dict = {}
    pending: tuple[str, str] | None = None
    current = 'A'
    for page in LISTS_PAGES:
        for raw in pages.get(page, []):
            if re.search(r'MINIMUM\s+RATES|LIST\s+C\b', raw):
                current = 'C'
            if re.search(r'LIST\s+D\b|RATE TO BE APPLIED BY', raw):
                current = 'D'
            if current == 'D':
                continue
            codes = LIST_CODE.findall(raw)
            tokens = _list_tokens(raw)
            if codes:
                code = '.'.join(codes[-1])
                if len(tokens) == 14:
                    national[code] = {'rate': tokens[BARBADOS_COLUMN], 'list': current, 'cet': tokens[0]}
                    pending = None
                else:
                    pending = (code, current)
            elif pending and len(tokens) == 14:
                national[pending[0]] = {'rate': tokens[BARBADOS_COLUMN], 'list': pending[1], 'cet': tokens[0]}
                pending = None
    return national


def parse_tariff(source: Path) -> dict:
    pages = _pages(source)
    lines, skipped = parse_section_a(pages)
    return {'lines': lines, 'skipped': skipped, 'section_b': parse_section_b(pages), 'section_c': parse_section_c(pages), 'lists': parse_list_rows(pages)}


SYNONYMS = {'chicken': 'fowl', 'beef': 'bovine', 'cattle': 'bovine', 'cow': 'bovine', 'pork': 'swine', 'pig': 'swine', 'hog': 'swine', 'lamb': 'sheep', 'mutton': 'sheep'}


class BarbadosCalculator(Calculator):
    name = 'Barbados'
    currency = 'BBD'

    def __init__(self):
        self.lines: list[dict] = []
        self.by_code: dict[str, dict] = {}
        self.section_b: list[dict] = []
        self.section_c: dict[str, dict] = {}
        self.lists: dict = {}
        self.loaded_at: str | None = None

    # ------------------------------------------------------------ data
    @property
    def path(self) -> Path:
        return FOLDER / 'tariff.json'

    def refresh(self) -> dict:
        sources = sorted(KNOWLEDGE_BASE.glob('*arbados*customs*.md'), key=lambda item: item.stat().st_mtime)
        if not sources:
            raise ValueError('The Barbados customs duties file is not in the knowledge base (documents/knowledge_base/*Barbados customs duties*.md).')
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
        self.section_b, self.section_c, self.lists = data.get('section_b', []), data.get('section_c', {}), data.get('lists', {})
        for line in data['lines']:
            override = overrides.get(line['code'])
            line['overridden'] = bool(override)
            if override:
                line.update({key: value for key, value in override.items() if key in ('duty', 'vat', 'units')}, status='ok', note='corrected by hand (overrides.json)', duty_specific=None)
            self.lines.append(line)
            self.by_code[line['code']] = line
            self.by_code.setdefault(digits(line['code']), line)
        self.loaded_at = datetime.fromtimestamp(self.path.stat().st_mtime).strftime('%Y-%m-%d')

    def _ensure(self) -> None:
        if not self.lines:
            self._load()

    def _list_value(self, line: dict) -> dict | None:
        return self.lists.get(line['code'][:10])

    def info(self) -> dict:
        self._ensure()
        conflicts = sum(1 for line in self.lines if line['duty'] and self._list_value(line) and self._list_value(line)['rate'] != line['duty'])
        return {
            'country': self.name,
            'ready': bool(self.lines),
            'lines': len(self.lines),
            'source': 'Barbados Customs Tariff (S.I. 2019 No. 57; revised CET, HS 2017) — knowledge base',
            'data_date': self.loaded_at,
            'can_refresh': True,
            'refresh_note': 'Re-reads the Barbados customs duties file uploaded to the knowledge base.',
            'currency': self.currency,
            'review_lines': sum(1 for line in self.lines if line['status'] == 'review'),
            'section_b_entries': len(self.section_b),
            'section_c_entries': len(self.section_c),
            'schedule_vs_list_conflicts': conflicts,
        }

    def signature(self, line: dict):
        listed = self._list_value(line)
        return ('60%' if self._section_b(line) else (higher_rate(line['duty'], listed['rate']) if listed and line['duty'] else line['duty']), line['extra'], line['vat'])

    # ------------------------------------------------------------ rules lookups
    def _section_b(self, line: dict) -> dict | None:
        code = digits(line['code'])
        best = None
        for entry in self.section_b:
            if code.startswith(entry['code']) and (best is None or len(entry['code']) > len(best['code'])):
                best = entry
        return best

    def _section_c(self, line: dict) -> dict | None:
        code = digits(line['code'])
        best = None
        for key, entry in self.section_c.items():
            if code.startswith(key) and (best is None or len(key) > len(digits(best['code']))):
                best = entry
        return best

    # ------------------------------------------------------------ lookup
    def _summary(self, line: dict) -> str:
        parts = []
        section_b = self._section_b(line)
        if section_b:
            parts.append(f"Customs duty 60% (Section B{' ex' if section_b['ex'] else ''}; Section A {line['duty'] or line['duty_specific'] or 'n/a'})")
        elif line['duty']:
            listed = self._list_value(line)
            used = higher_rate(line['duty'], listed['rate']) if listed else line['duty']
            parts.append(f"Customs duty {used}" + (f" (schedule {line['duty']}, List {listed['rate']})" if listed and listed['rate'] != line['duty'] else ''))
        else:
            parts.append(f"Customs duty {line['duty_specific'] or 'not legible'}")
        if line['extra_kind'] == 'excise_pct':
            parts.append(f"excise {line['extra']}")
        if line['inspection_fee']:
            label = {'inspection': 'inspection fee', 'countervailing': 'countervailing duty', 'excise_specific': 'excise'}.get(line['extra_kind'], 'additional charge')
            parts.append(f"{label} {line['inspection_fee']}")
        if line['vat']:
            parts.append('VAT ' + ('0%' if line['vat'] == '0.0%' else line['vat']))
        if self._section_c(line):
            parts.append('special safeguard may apply')
        return '; '.join(parts)

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
            raise ValueError(f'Tariff line {code} not found in the Barbados tariff.')
        cif = inputs.goods_value_usd + inputs.freight_usd + inputs.insurance_usd
        result = Result(
            country=self.name,
            line=self._public(line),
            inputs=inputs.__dict__.copy(),
            value_basis={'name': 'CIF value', 'amount_usd': round(cif, 2), 'formula': f'goods {money(inputs.goods_value_usd)} + freight {money(inputs.freight_usd)} + insurance {money(inputs.insurance_usd)}'},
            sources=[f"Barbados Customs Tariff (S.I. 2019 No. 57), Part 1 Section A, line {line['code']}, page {line['page']} of the file"],
        )
        result.notes.append(f'Duty is charged on the CIF value (goods + freight + insurance); the Barbados dollar is pegged at BBD {BBD_PER_USD:g} per US$.')
        origin = (inputs.origin or '').strip().lower()
        caricom = origin in CARICOM

        # ---- customs duty: Section A, or 60% when the goods are in Part 1 Section B
        section_b = self._section_b(line)
        duty_text = line['duty']
        if section_b:
            result.notes.append(f"This line is in Part 1 Section B (listed under {section_b['raw']}): a 60% duty applies notwithstanding Section A ({line['duty'] or line['duty_specific'] or 'n/a'}).")
            if section_b['ex']:
                hint = f" Text printed with the entry: {section_b['text']}" if section_b['text'] else ''
                result.warnings.append(f"Section B lists these goods as \"ex {section_b['raw']}\": only part of the heading pays 60% (some products are excluded).{hint} Check whether this product is covered.")
            duty_text = '60%'
        listed = self._list_value(line)
        if listed and not section_b and line['duty']:
            duty_text = higher_rate(line['duty'], listed['rate'])  # standing rule: when the schedule and the List disagree, the higher rate is used
        if caricom:
            result.notes.append(f'{inputs.origin} is a CARICOM member: goods that qualify for Community treatment (certificate of origin) enter free of the Common External Tariff.')
            result.taxes.append(Tax('Customs duty', 0.0, '0% (CARICOM origin)', 'CIF value', f"CARICOM origin: duty waived (tariff rate {duty_text or line['duty_specific'] or 'not legible'})"))
        elif duty_text == 'Free':
            result.taxes.append(Tax('Customs duty', 0.0, 'Free', 'CIF value', 'free of duty'))
        elif duty_text and duty_text.endswith('%'):
            pct = float(duty_text.rstrip('%'))
            result.taxes.append(Tax('Customs duty', cif * pct / 100, duty_text, 'CIF value', f'{money(cif)} × {pct:g}%'))
        else:
            result.complete = False
            result.warnings.append(f"The duty of line {line['code']} is a specific amount or could not be read from the file ({line['duty_specific'] or line['specific_text'] or 'no rate'}; page {line['page']}); it is not in the total.")
        if line['status'] == 'review' and duty_text:
            result.warnings.append(f"Verify this line on page {line['page']}: {line['note']}")

        # ---- Special Safeguard additional duty (Section C)
        trigger = self._section_c(line)
        if trigger and not caricom:
            if inputs.quantity_kg:
                price_bbd = cif / inputs.quantity_kg * BBD_PER_USD
                extra = safeguard_additional_duty(trigger['trigger_bbd_per_kg'], price_bbd)
                if extra > 0:
                    result.taxes.append(Tax('Special safeguard additional duty', extra * inputs.quantity_kg / BBD_PER_USD, f"trigger BBD {trigger['trigger_bbd_per_kg']:.2f}/kg", 'kg',
                                            f"trigger BBD {trigger['trigger_bbd_per_kg']:.2f}/kg, CIF price BBD {price_bbd:.2f}/kg: additional duty BBD {extra:.4f}/kg × {inputs.quantity_kg:g} kg ÷ {BBD_PER_USD:g}"))
                outcome = f'BBD {extra:.4f} per kg' if extra > 0 else 'none (the CIF price is within 10% of the trigger, or above it)'
                result.notes.append(f"This line is in Part 1 Section C (Special Safeguard, trigger price BBD {trigger['trigger_bbd_per_kg']:.2f} per kg). Additional duty: {outcome}.")
            else:
                result.complete = False
                result.warnings.append(f"This line is in Part 1 Section C: a Special Safeguard additional duty applies when the CIF price per kg is more than 10% below the trigger price (BBD {trigger['trigger_bbd_per_kg']:.2f}/kg). Enter the quantity in kg to compute it.")
            result.warnings.append('The safeguard duty is charged where no quota allocation has been granted for the goods; this calculator assumes none was granted.')

        # ---- the middle column: inspection fee, countervailing duty or excise
        if line['extra_kind'] == 'countervailing':
            amount = re.search(r'\$\s?([\d.]+)\s*per\s*l', line['inspection_fee'] or '')
            if origin == 'trinidad and tobago' and amount:
                if inputs.quantity_units is None:
                    result.complete = False
                    result.warnings.append(f"Countervailing duty of {line['inspection_fee']} applies to goods from Trinidad and Tobago: enter the quantity in litres (units) to include it.")
                else:
                    per_litre = float(amount.group(1)) / BBD_PER_USD
                    result.taxes.append(Tax('Countervailing duty (goods from Trinidad and Tobago)', inputs.quantity_units * per_litre, f'BBD {float(amount.group(1)):g} per litre', 'litre', f'{inputs.quantity_units:g} l × BBD {float(amount.group(1)):g} ÷ {BBD_PER_USD:g}'))
            elif origin == 'trinidad and tobago':
                result.complete = False
                result.warnings.append(f"This line carries a countervailing charge for goods from Trinidad and Tobago that could not be read: {line['inspection_fee']}.")
            else:
                result.notes.append(f"A countervailing duty ({line['inspection_fee']}) applies only to goods from Trinidad and Tobago; not charged for {inputs.origin or 'this origin'}.")
        elif line['extra_kind'] == 'excise_pct':
            rate = float(line['extra'].rstrip('%'))
            base = cif + sum(tax.amount for tax in result.taxes)
            result.taxes.append(Tax('Excise tax', base * rate / 100, line['extra'], 'CIF value + duty', f'({money(base)}) × {rate:g}%', note='The file does not state the excise base; CIF value + duty is assumed.'))
        elif line['inspection_fee']:
            fee = line['inspection_fee']
            each = re.match(r'^\$\s?([\d.,]+)\s*each', fee)
            if each and 'batch' not in fee:
                per = float(each.group(1).replace(',', '')) / BBD_PER_USD
                if inputs.quantity_units is None:
                    result.complete = False
                    result.warnings.append(f'An inspection fee of {fee} applies: enter the number of head (units) to include it.')
                else:
                    result.taxes.append(Tax('Inspection fee', inputs.quantity_units * per, fee, 'each', f'{inputs.quantity_units:g} × BBD {float(each.group(1)):g} ÷ {BBD_PER_USD:g}'))
            else:
                result.complete = False
                result.warnings.append(f'This line carries an inspection fee written "{fee}", which this calculator does not compute; it is not in the total.')
        elif line['extra_kind'] in ('excise_specific', 'other') or (line['extra'] and not line['extra_kind']):
            result.complete = False
            result.warnings.append(f"This line carries a {'specific excise' if line['extra_kind'] == 'excise_specific' else 'charge'} written \"{line['inspection_fee'] or line['extra']}\" that this calculator does not compute; it is not in the total.")
        if line['specific_text'] and line['duty']:
            result.complete = False
            result.warnings.append(f"Specific amount(s) are printed with this line ({line['specific_text']}): excise or fuel tax per unit. They are not in the total.")

        # ---- VAT: the rate printed on the line, on CIF + duty + excise + safeguard
        vat_text = line['vat'] or '17.5%'
        vat_rate = float(vat_text.rstrip('%'))
        base = cif + sum(tax.amount for tax in result.taxes if not tax.recoverable)
        result.taxes.append(
            Tax('Value added tax (VAT)', base * vat_rate / 100, f'{vat_rate:g}%', 'CIF value + duty + excise', f'({money(base)}) × {vat_rate:g}%', recoverable=True,
                note=('Zero-rated on this tariff line. ' if vat_rate == 0 else '') + 'Not counted: a VAT-registered importer credits it.')
        )

        # ---- origin, EPA and cross-checks
        if origin in EPA_ORIGINS:
            result.warnings.append(f'{inputs.origin} is an EPA partner. The file lists "EPA rates until 2020" (pages 719-1053), which are not applied: the normal rate is shown, which may be higher than the current EPA rate.')
        elif inputs.origin and not caricom:
            result.notes.append(f'No origin preference is applied for {inputs.origin}: the standard rate applies.')
        if listed and line['duty'] and listed['rate'] != line['duty'] and not section_b:
            result.warnings.append(f"CONFLICT IN THE FILE: the schedule gives this line {line['duty']} (page {line['page']}) but List {listed['list']} gives Barbados {listed['rate']}. The HIGHER rate ({duty_text}) is used; check which one Barbados Customs collects.")
        result.warnings.append('Not included: duty exemptions for approved purposes (List of Conditional Duty Exemptions), import licences and sanitary/phytosanitary permits, and any fee or levy that is not printed in the tariff. The tariff is the HS 2017 edition (11 April 2018, amended 2019).')
        return result
